"""Colorado 14er Phase 3: segment-safe recorded-track features and QA.

Python 3.10+, numpy and the existing block1_scraper runtime dependencies.
No HTTP requests, itinerary assembly, timestamp features, or automatic scope approval.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from defusedxml import ElementTree as ET

FEATURE_VERSION = '3.1.0'
M_PER_MILE = 1609.344
FT_PER_M = 3.280839895
GEOMETRY_FEATURES = ('distance_mi', 'gain_ft', 'crux_density_medium',
                     'crux_density_extreme', 'crux_medium_mi', 'crux_extreme_mi',
                     'steep_above20_mi', 'longest_medium_mi', 'longest_extreme_mi',
                     'longest_above20_mi')
RISKS = ('exposure', 'rockfall', 'route_finding', 'commitment')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def distance(a, b):
    p, q = math.radians(a[0]), math.radians(b[0])
    h = math.sin((q-p)/2)**2 + math.cos(p)*math.cos(q)*math.sin(math.radians(b[1]-a[1])/2)**2
    return 6371008.8 * 2 * math.asin(math.sqrt(min(1.0, max(0.0, h))))


def sequences(body):
    """Read only track/route points, keeping every GPX sequence boundary."""
    root = ET.fromstring(body)
    tag = lambda n: n.tag.rsplit('}', 1)[-1]
    result = []
    for node in root.iter():
        if tag(node) not in ('trkseg', 'rte'):
            continue
        points = []
        for point in node:
            if tag(point) not in ('trkpt', 'rtept'):
                continue
            elevation = next((float(c.text) for c in point if tag(c) == 'ele'), None)
            points.append((float(point.attrib['lat']), float(point.attrib['lon']), elevation))
        if len(points) >= 2:
            result.append(points)
    return result


def validated_runs(seqs, params):
    """Invalid edges split profiles; no interpolation or crux run crosses them."""
    runs, counts, total, accepted = [], Counter(), 0.0, 0.0
    for seq in seqs:
        run = [seq[0]]
        for a, b in zip(seq, seq[1:]):
            d = distance(a, b)
            total += d
            reason = None
            if d < params['min_horizontal_step_m']:
                reason = 'near_zero_step'
            elif d > params['max_horizontal_step_m'] and not math.isclose(
                    d, params['max_horizontal_step_m'], rel_tol=0, abs_tol=1e-7):
                reason = 'long_gap'
            elif a[2] is None or b[2] is None:
                reason = 'missing_elevation'
            elif abs(b[2]-a[2])/d * 100 > params['max_abs_grade_pct']:
                reason = 'implausible_grade'
            if reason:
                counts[reason] += 1
                if len(run) >= 2:
                    runs.append(run)
                run = [b]
            else:
                accepted += d
                run.append(b)
        if len(run) >= 2:
            runs.append(run)
    return runs, {'recorded_distance_m': total, 'accepted_distance_m': accepted,
                  'valid_distance_fraction': accepted/total if total else 0.0,
                  **{k: counts[k] for k in ('near_zero_step', 'long_gap', 'missing_elevation', 'implausible_grade')}}


def accepted_segment_densities(profile, qa):
    """Describe observed segments; bound unknown excluded chord lengths, never fill them."""
    fraction = qa['valid_distance_fraction']
    result = {'observed_segment_scope': 'accepted_recorded_segments_only',
              'excluded_recorded_distance_fraction': 1-fraction}
    for band in ('medium', 'extreme'):
        value = profile['crux_density_'+band]
        prefix = 'observed_segment_crux_density_'+band
        result[prefix] = value
        # Chord-distance bounds conditional on the recorded polyline, not true terrain length.
        result['recorded_chord_crux_density_'+band+'_lower_pct'] = value*fraction if value is not None else None
        result['recorded_chord_crux_density_'+band+'_upper_pct'] = min(100, value*fraction+100*(1-fraction)) if value is not None else None
    return result


def smooth_profile(x, z, window):
    """Distance-window mean with linear endpoint extension; keeps a linear slope."""
    if window <= 0 or len(x) < 3:
        return z.copy()
    step = x[1]-x[0]
    half = int(math.floor(window/(2*step)))
    if half == 0:
        return z.copy()
    left = z[0] - np.arange(half, 0, -1) * (z[1]-z[0])
    right = z[-1] + np.arange(1, half+1) * (z[-1]-z[-2])
    return np.convolve(np.concatenate((left, z, right)), np.ones(2*half+1)/(2*half+1), mode='valid')


def profile_edges(runs, interval, window):
    edges = []
    for run in runs:
        dx = np.array([distance(a, b) for a, b in zip(run, run[1:])])
        x = np.concatenate(([0.0], np.cumsum(dx)))
        z = np.array([p[2] for p in run], dtype=float)
        if interval:
            # Equal spacing includes both endpoints and never exceeds the chosen interval.
            grid = np.linspace(0.0, x[-1], max(1, math.ceil(x[-1]/interval))+1)
            z = np.interp(grid, x, z)
            x = grid
        z = smooth_profile(x, z, window)
        edges.append((np.diff(x), np.diff(z)))
    return edges


def longest_run(dx, mask):
    longest = current = 0.0
    for d, active in zip(dx, mask):
        current = current + float(d) if active else 0.0
        longest = max(longest, current)
    return longest


def summarize_edges(edges, params):
    totals = Counter()
    longest = Counter()
    for dx, dz in edges:
        grade = np.abs(dz/dx)*100
        # Avoid numerical jitter assigning an exact boundary to different bands.
        for boundary in (params['medium_grade_min_pct'], params['extreme_grade_min_pct']):
            grade[np.isclose(grade, boundary, rtol=0, atol=1e-9)] = boundary
        medium = (grade >= params['medium_grade_min_pct']) & (grade <= params['extreme_grade_min_pct'])
        extreme = grade > params['extreme_grade_min_pct']
        above20 = medium | extreme
        totals['distance'] += float(dx.sum())
        totals['gain'] += float(np.maximum(dz, 0).sum())
        for key, mask in [('medium', medium), ('extreme', extreme), ('above20', above20)]:
            totals[key] += float(dx[mask].sum())
            longest[key] = max(longest[key], longest_run(dx, mask))
    length = totals['distance']
    return {'distance_mi': length/M_PER_MILE if length else None,
            'gain_ft': totals['gain']*FT_PER_M if length else None,
            'crux_density_medium': 100*totals['medium']/length if length else None,
            'crux_density_extreme': 100*totals['extreme']/length if length else None,
            'crux_medium_mi': totals['medium']/M_PER_MILE if length else None,
            'crux_extreme_mi': totals['extreme']/M_PER_MILE if length else None,
            'steep_above20_mi': totals['above20']/M_PER_MILE if length else None,
            'longest_medium_mi': longest['medium']/M_PER_MILE if length else None,
            'longest_extreme_mi': longest['extreme']/M_PER_MILE if length else None,
            'longest_above20_mi': longest['above20']/M_PER_MILE if length else None}


def analyze_track(seqs, params):
    runs, qa = validated_runs(seqs, params)
    raw = summarize_edges(profile_edges(runs, None, 0), params)
    profile = summarize_edges(profile_edges(runs, params['resample_interval_m'], params['smoothing_window_m']), params)
    sensitivity = []
    for interval in params['sensitivity_intervals_m']:
        for window in params['sensitivity_windows_m']:
            sensitivity.append(summarize_edges(profile_edges(runs, interval, window), params))
    for key, field in [('crux_density_medium', 'density_medium_range_pp'),
                       ('crux_density_extreme', 'density_extreme_range_pp'), ('gain_ft', 'gain_range_ft')]:
        values = [x[key] for x in sensitivity if x[key] is not None]
        qa[field] = max(values)-min(values) if values else None
    qa['gain_sensitivity_pct'] = 100*qa['gain_range_ft']/profile['gain_ft'] if profile['gain_ft'] else None
    return profile, raw, qa, runs


def occupied_cells(runs, grid_m):
    """Coarse equirectangular screening only; never infer exact itinerary equality."""
    cells = set()
    for run in runs:
        for a, b in zip(run, run[1:]):
            n = max(1, math.ceil(distance(a, b)/(grid_m/2)))
            for t in np.linspace(0, 1, n+1):
                lat, lon = a[0]+t*(b[0]-a[0]), a[1]+t*(b[1]-a[1])
                x = 6371008.8*math.radians(lon+106)*math.cos(math.radians(39))
                y = 6371008.8*math.radians(lat-39)
                cells.add((math.floor(x/grid_m), math.floor(y/grid_m)))
    return cells


def evaluation_groups(rows, cell_sets, threshold):
    ids = [r['route_id'] for r in rows]
    parent = {rid: rid for rid in ids}
    def find(rid):
        while parent[rid] != rid:
            parent[rid] = parent[parent[rid]]
            rid = parent[rid]
        return rid
    def union(a, b):
        parent[find(b)] = find(a)
    for row in rows:
        for other in row.get('evaluation_group', '').split('|'):
            if other in parent:
                union(row['route_id'], other)
    links = []
    for i, a in enumerate(ids):
        for b in ids[i+1:]:
            size = min(len(cell_sets.get(a, set())), len(cell_sets.get(b, set())))
            if not size:
                continue
            fraction = len(cell_sets[a] & cell_sets[b])/size
            if fraction >= threshold:
                union(a, b)
                links.append({'a': a, 'b': b, 'shorter_track_cell_overlap': fraction})
    groups = {}
    for rid in ids:
        groups.setdefault(find(rid), []).append(rid)
    return {rid: '|'.join(sorted(groups[find(rid)])) for rid in ids}, links


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')
    tmp.replace(path)


def run_features(project_root, data_root, feature_path, report_path):
    project_root, data_root = Path(project_root), Path(data_root)
    artifact_root = project_root/'outputs' if (project_root/'outputs/project_config.json').exists() else project_root
    config_path = artifact_root/'project_config.json'
    config = json.loads(config_path.read_text())
    params = config['phase3']['parameters']
    if config['phase3']['feature_version'] != FEATURE_VERSION or params['threshold_unit'] != 'percent_grade':
        raise ValueError('Feature version/unit differs from implementation')
    if not (0 <= params['medium_grade_min_pct'] < params['extreme_grade_min_pct'] < params['max_abs_grade_pct']):
        raise ValueError('Invalid grade thresholds')
    spec = importlib.util.spec_from_file_location('feature_ingestion', artifact_root/'block1_scraper.py')
    ingestion = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ingestion)
    audit_spec = importlib.util.spec_from_file_location('feature_audit', project_root/'scripts/audit_phase2.py')
    audit = importlib.util.module_from_spec(audit_spec)
    audit_spec.loader.exec_module(audit)
    snapshot = audit.audit(data_root, project_root)
    if not snapshot['snapshot_integrity_passed']:
        raise ValueError('Ingestion snapshot failed integrity: '+str(snapshot['errors']))
    with (data_root/'route_status.csv').open(newline='') as f:
        statuses = list(csv.DictReader(f))
    catalog = {x['source_url']: x for x in json.loads((data_root/'catalog.json').read_text())}
    risks = config['feature_contract']['risk_encoding']
    output, cells, source_hashes = [], {}, {}
    for status in statuses:
        rid = status['route_id']
        path = data_root/'gpx'/f'{rid}.gpx'
        sidecar = json.loads(path.with_suffix('.json').read_text())
        row = {k: status.get(k, '') for k in ('route_id', 'canonical_name', 'source_url', 'manifest_version',
                'evaluation_group', 'start_name', 'descent_policy', 'itinerary_verified', 'dry_summer_verified',
                'coverage_review_priority', 'endpoint_gap_m')}
        row.update(feature_version=FEATURE_VERSION, feature_scope='recorded_source_track', feature_eligible=False)
        flags = []
        source = catalog.get(status['source_url'])
        reviewed_export = status.get('ingestion_method') == 'approved_local_export'
        if reviewed_export:
            required = ('reviewer', 'review_date', 'source_references', 'metadata_evidence',
                        'geometry_evidence', 'conditions_evidence', 'export_sha256', 'permission_evidence')
            if not all(sidecar.get(k) for k in required):
                raise ValueError(rid+': reviewed export lacks scope evidence')
            for key in ('start_policy', 'summit_order', 'descent_policy'):
                if sidecar.get(key) != status.get(key):
                    raise ValueError(rid+': reviewed export itinerary changed')
            for key in ('itinerary_verified', 'dry_summer_verified'):
                if type(sidecar.get(key)) is not bool or sidecar[key] != (status.get(key) == 'true'):
                    raise ValueError(rid+': reviewed export scope flags changed')
            source = {k: sidecar[k] for k in ('yds_raw', 'yds_class', 'source_distance_mi',
                      'source_gain_ft', *(r+'_raw' for r in RISKS))}
            source.update(source_url=status['source_url'], source_html_sha256='',
                          yds_encoded=config['yds_encoding'][str(source['yds_class'])])
            row['metadata_provenance'] = 'reviewed_export:'+sidecar['export_sha256']
        else:
            row['metadata_provenance'] = 'captured_official_overview'
        if source is None:
            raise ValueError(rid+': missing acquired source metadata')
        effective = ingestion.apply_selection_metadata(status, source)
        # Check metadata against the immutable captured overview, rather than trusting CSV edits.
        for key in ('yds_raw', 'yds_class', 'yds_encoded'):
            value = effective.get(key)
            if value is None:
                raise ValueError(rid+': missing class')
            if key == 'yds_raw':
                if status.get(key) != str(value):
                    raise ValueError(rid+': metadata mismatch '+key)
            elif float(status[key]) != value:
                raise ValueError(rid+': encoding mismatch '+key)
            row[key] = value
        row['source_html_sha256'] = source['source_html_sha256']
        for risk in RISKS:
            label = status[risk+'_raw']
            if label != source[risk+'_raw'] or label not in risks:
                raise ValueError(rid+': unknown or altered source risk '+risk)
            row[risk+'_raw'], row[risk+'_encoded'] = label, risks[label]
        for key in ('source_distance_mi', 'source_gain_ft'):
            value = effective.get(key)
            supplied = float(status[key]) if status.get(key) else None
            if supplied != value:
                raise ValueError(rid+': published metric changed '+key)
            row[key] = value
        if status.get('metadata_complete', '').lower() != 'true':
            flags.append('metadata_scope_pending')
        if status.get('itinerary_verified') != 'true' or status.get('dry_summer_verified') != 'true':
            flags.append('complete_dry_itinerary_unverified')
        body = path.read_bytes()
        quality = ingestion.validate_gpx(body)
        if not reviewed_export and sidecar.get('source_html_sha256') != source['source_html_sha256']:
            raise ValueError(rid+': overview provenance mismatch')
        receipt = sidecar.get('acquisition_receipt')
        if receipt and receipt.get('metadata_sha256') != source['source_html_sha256']:
            raise ValueError(rid+': acquisition overview hash mismatch')
        row['gpx_sha256'] = quality['gpx_sha256']
        row['geometry_sha256'] = quality['geometry_sha256']
        source_hashes[rid] = {'gpx': row['gpx_sha256'], 'overview': row['source_html_sha256'],
                              'reviewed_export': sidecar.get('export_sha256', '')}
        if status.get('itinerary_verified') == 'true' and not all(sidecar.get(k) for k in
                ('reviewer', 'review_date', 'geometry_evidence', 'conditions_evidence')):
            flags.append('scope_review_evidence_missing')
        profile, raw, qa, runs = analyze_track(sequences(body), params)
        cells[rid] = occupied_cells(runs, params['overlap_grid_m'])
        row.update({'source_track_'+k: v for k, v in profile.items()})
        row.update({'raw_track_'+k: v for k, v in raw.items()})
        row.update({'profile_'+k: v for k, v in qa.items()})
        row.update(accepted_segment_densities(profile, qa))
        if qa['valid_distance_fraction'] < params['min_valid_distance_fraction']:
            flags.append('insufficient_valid_profile_coverage')
        if any(qa[k] for k in ('long_gap', 'missing_elevation', 'implausible_grade')):
            flags.append('profile_edges_excluded')
        if profile['distance_mi'] is None:
            flags.append('no_valid_profile')
        if any(qa[k] is not None and qa[k] > params['max_density_sensitivity_pp']
               for k in ('density_medium_range_pp', 'density_extreme_range_pp')):
            flags.append('density_sensitive_to_parameters')
        if qa['gain_sensitivity_pct'] is not None and qa['gain_sensitivity_pct'] > params['max_gain_sensitivity_pct']:
            flags.append('gain_sensitive_to_parameters')
        if qa['valid_distance_fraction'] < params['min_valid_distance_fraction']:
            # Keep the miles of accepted observations, but do not claim route-wide densities.
            for key in ('crux_density_medium', 'crux_density_extreme'):
                row['source_track_'+key] = None
        for feature, source_key in [('distance_mi', 'source_distance_mi'), ('gain_ft', 'source_gain_ft')]:
            total = row[source_key]
            measured = profile[feature]
            ratio = measured/total if total and measured is not None else None
            row['recorded_to_published_'+feature+'_ratio'] = ratio
            # A mismatch on an unreviewed ascent file is diagnostic, not a false full-route test.
            if status.get('itinerary_verified') == 'true' and ratio is not None:
                limit = params['distance_discrepancy_fraction' if feature == 'distance_mi' else 'gain_discrepancy_fraction']
                if abs(ratio-1) > limit:
                    flags.append(feature+'_scope_discrepancy')
        row['profile_qa_pass'] = not any(x not in ('complete_dry_itinerary_unverified', 'metadata_scope_pending') for x in flags)
        row['feature_eligible'] = status.get('training_eligible', '').lower() == 'true' and row['profile_qa_pass']
        for key in GEOMETRY_FEATURES:
            row[key] = profile[key] if row['feature_eligible'] else None
        row['feature_scope'] = 'complete_reviewed_itinerary' if row['feature_eligible'] else 'recorded_source_track'
        row['qa_flags'] = '|'.join(flags)
        output.append(row)
    groups, links = evaluation_groups(output, cells, params['overlap_fraction_threshold'])
    for row in output:
        row['evaluation_group'] = groups[row['route_id']]
    feature_path = Path(feature_path)
    feature_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = feature_path.with_suffix('.csv.tmp')
    fields = list(dict.fromkeys(k for row in output for k in row))
    with tmp.open('w', newline='') as f:
        writer = csv.DictWriter(f, fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(output)
    tmp.replace(feature_path)
    flags = Counter(flag for row in output for flag in row['qa_flags'].split('|') if flag)
    eligible = sum(row['feature_eligible'] for row in output)
    review = {'feature_version': FEATURE_VERSION, 'manifest_version': config['manifest_version'],
              'manifest_sha256': config['manifest_sha256'], 'config_sha256': digest(config_path),
              'implementation_sha256': digest(artifact_root/'block2_features.py'),
              'source_provenance_sha256': hashlib.sha256(json.dumps(source_hashes, sort_keys=True).encode()).hexdigest(),
              'input_catalog_sha256': digest(data_root/'catalog.json'),
              'input_status_sha256': digest(data_root/'route_status.csv'),
              'feature_table_sha256': digest(feature_path), 'run_at': datetime.now(timezone.utc).isoformat(),
              'runtime': {'numpy': np.__version__, 'python': ingestion.sys.version.split()[0]},
              'snapshot_integrity_passed': snapshot['snapshot_integrity_passed'],
              'parameters': params, 'route_count': len(output), 'recorded_profiles_computed': len(output),
              'class_and_risk_encodings_complete': sum(all(row.get(k) is not None for k in
                  ('yds_encoded', *(r+'_encoded' for r in RISKS))) for row in output),
              'profile_qa_pass_count': sum(row['profile_qa_pass'] for row in output),
              'feature_eligible_count': eligible, 'phase3_engineering_complete': True,
              'phase3_dataset_ready': eligible == len(output) == 100,
              'phase4_engineering_ready': True, 'phase4_complete_itinerary_pca_ready': eligible == len(output) == 100,
              'qa_flag_counts': dict(flags), 'approximate_overlap_link_count': len(links),
              'evaluation_groups': sorted(set(groups.values())),
              'overlap_screening_note': '50m grid common-cell fraction of shorter recorded path; coarse candidates, not exact duplicates or verified full-itinerary overlaps.',
              'remaining_work': ['Review complete dry start/branch/summit/descent coverage and document assemblies.',
                                 'Resolve Culebra gain units and North Eolus complete-itinerary totals.',
                                 'Review excluded edges and sensitivity before freezing feature parameters.',
                                 'Review approximate spatial-overlap groups before model evaluation.']}
    atomic_json(report_path, review)
    return review


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument('--project-root', type=Path, default=root)
    parser.add_argument('--data-root', type=Path, default=root/'private_data/raw')
    parser.add_argument('--features', type=Path, default=root/'private_data/routes_features.csv')
    parser.add_argument('--report', type=Path, default=root/'outputs/phase3_review.json')
    args = parser.parse_args()
    result = run_features(args.project_root, args.data_root, args.features, args.report)
    print(json.dumps({k: result[k] for k in ('route_count', 'recorded_profiles_computed',
          'class_and_risk_encodings_complete', 'profile_qa_pass_count', 'feature_eligible_count',
          'phase3_dataset_ready', 'qa_flag_counts', 'approximate_overlap_link_count')}, indent=2))
