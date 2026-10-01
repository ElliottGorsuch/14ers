"""Audit a private ingestion snapshot; publish aggregate readiness, never raw GPX."""
import argparse
import csv
import hashlib
import json
import importlib.util
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def audit(data_root, project_root=ROOT):
    project_root, data_root = Path(project_root), Path(data_root)
    artifact_root = project_root/'outputs' if (project_root/'outputs/project_config.json').exists() else project_root
    config = json.loads((artifact_root/'project_config.json').read_text())
    manifest = artifact_root/'research_route_manifest.csv'
    with manifest.open(newline='') as f:
        roster = list(csv.DictReader(f))
    errors = []
    def check(ok, message):
        if not ok:
            errors.append(message)
    with (data_root/'route_status.csv').open(newline='') as f:
        rows = list(csv.DictReader(f))
    provenance = json.loads((data_root/'run_provenance.json').read_text())
    summary = json.loads((data_root/'run_summary.json').read_text())
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    check(digest == config['manifest_sha256'], 'Frozen manifest checksum mismatch')
    check(provenance.get('manifest_sha256') == digest, 'Run uses another manifest')
    check((data_root/'manifest_snapshot.csv').exists() and
          hashlib.sha256((data_root/'manifest_snapshot.csv').read_bytes()).hexdigest() == digest,
          'Private manifest snapshot differs from frozen roster')
    byid = {r['route_id']: r for r in roster}
    check(len(rows) == 100 and len({r.get('route_id') for r in rows}) == 100, 'Snapshot must contain 100 distinct selections')
    check({r.get('route_id') for r in rows} == set(byid), 'Snapshot IDs differ from roster')
    spec = importlib.util.spec_from_file_location("ingestion", artifact_root/"block1_scraper.py")
    ingestion = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ingestion)
    downloaded = eligible = verified_files = xml_verified = 0
    geometry_hashes = set()
    for row in rows:
        rid = row.get('route_id', '?')
        reference = byid.get(rid, {})
        for field in ('canonical_name', 'requested_name', 'manifest_version', 'start_policy', 'descent_policy', 'summit_order'):
            check(row.get(field) == reference.get(field), rid + ': frozen field differs: ' + field)
        selected = row.get('training_eligible', '').lower() == 'true'
        if selected:
            eligible += 1
            check(row.get('status') == 'downloaded', rid + ': eligible without downloaded geometry')
            check(row.get('itinerary_verified') == 'true' and row.get('dry_summer_verified') == 'true', rid + ': eligible without reviewed scope')
            check(row.get('metadata_complete', '').lower() == 'true', rid + ': eligible with incomplete metadata')
            check(row.get('elevation_coverage') == '1.0', rid + ': eligible with missing elevations')
            check(row.get('yds_encoded') in ('1','2','4','8','16','1.0','2.0','4.0','8.0','16.0'), rid + ': invalid grade encoding')
            check(bool(row.get('evaluation_group')), rid + ': missing evaluation group')
        if row.get('status') != 'downloaded':
            continue
        downloaded += 1
        path = data_root/'gpx'/f'{rid}.gpx'
        sidecar = path.with_suffix('.json')
        if not path.exists() or not sidecar.exists():
            errors.append(rid + ': missing GPX/provenance')
            continue
        body = path.read_bytes()
        actual = hashlib.sha256(body).hexdigest()
        try:
            quality = ingestion.validate_gpx(body)
            check(str(float(quality['point_count'])) == str(float(row.get('point_count', 'nan'))), rid + ': point count differs from actual GPX')
            check(str(quality['elevation_coverage']) == row.get('elevation_coverage'), rid + ': elevation coverage differs from actual GPX')
            geometry_hashes.add(quality['geometry_sha256'])
            check(quality['geometry_sha256'] == row.get('geometry_sha256'), rid + ': normalized geometry hash differs')
            xml_verified += 1
        except (ingestion.IngestionError, ValueError, TypeError) as exc:
            errors.append(rid + ': invalid actual GPX: ' + str(exc))
        metadata = json.loads(sidecar.read_text())
        if actual == row.get('gpx_sha256') == metadata.get('gpx_sha256'):
            verified_files += 1
        else:
            errors.append(rid + ': GPX/provenance checksum mismatch')
    counts = dict(Counter(r.get('status') for r in rows))
    check(summary.get('downloaded') == downloaded and summary.get('training_eligible') == eligible,
          'Run summary disagrees with snapshot')
    check(summary.get('statuses') == counts, 'Status counts disagree with run summary')
    if downloaded == 100:
        check(len(geometry_hashes) == 100, 'Selected dataset contains exact geometry aliases')
    ready = not errors and downloaded == eligible == verified_files == 100
    return {
        'schema_version': '1.0.0', 'manifest_version': config['manifest_version'],
        'manifest_sha256': digest, 'ingestion_version': provenance.get('ingestion_version'),
        'snapshot_integrity_passed': not errors, 'selection_count': len(rows),
        'statuses': counts, 'downloaded': downloaded, 'checksum_verified_files': verified_files, 'xml_verified_files': xml_verified,
        'distinct_source_routes': len({r['source_url'] for r in roster if r['source_url']}),
        'distinct_geometry_files': len(geometry_hashes),
        'metadata_complete_count': sum(r.get('metadata_complete', '').lower() == 'true' for r in rows),
        'preliminary_training_eligible': eligible,
        'phase2_acceptance_complete': ready, 'phase3_dataset_ready': ready,
        'phase3_engineering_can_start_with_fixtures': True,
        'source_permission_status': config['source_access']['permission_status'],
        'raw_live_gpx_verified': bool(config['source_access'].get('browser_download_review', {}).get('gpx_downloads_verified') or config['source_access']['raw_http_smoke_test']['live_gpx_download_verified']),
        'direct_http_gpx_verified': config['source_access']['raw_http_smoke_test']['live_gpx_download_verified'],
        'browser_acquisition': config['source_access'].get('browser_download_review', {}),
        'curation_selection_ids': [r['route_id'] for r in roster if not r['source_url']],
        'remaining_selection_count': 100-eligible,
        'coverage_review_priorities': dict(Counter(r.get('coverage_review_priority', 'not_triaged') for r in rows)),
        'endpoint_gap_above_500m': sum(float(r.get('endpoint_gap_m') or 0) > 500 for r in rows),
        'metadata_review_ids': [r['route_id'] for r in rows if r.get('metadata_complete', '').lower() != 'true'],
        'phase3_additional_checks': ['sampling/gaps', 'elevation noise', 'complete-itinerary distance/gain discrepancies',
                                     'near-duplicate overlap', 'resampling/smoothing sensitivity'],
        'errors': errors,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', default=str(ROOT/'private_data/raw'))
    parser.add_argument('--out', default=str(ROOT/'outputs/phase2_review.json'))
    args = parser.parse_args()
    report = audit(args.data_root)
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix('.json.tmp')
    temp.write_text(json.dumps(report, indent=2)+'\n')
    temp.replace(target)
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report['snapshot_integrity_passed'] else 1)
