"""Validate the frozen Phase 1 contract and synchronized existing deliverables.

No network calls. Run from any directory with Python 3.10+.
"""
import ast
import csv
import hashlib
import json
import re
import zipfile
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def validate(root=ROOT):
    root = Path(root)
    out = root / 'outputs'
    config = json.loads((out / 'project_config.json').read_text())
    manifest = out / 'route_manifest.csv'
    raw = manifest.read_bytes()
    with manifest.open(encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = list(reader)
    errors = []
    def check(ok, message):
        if not ok:
            errors.append(message)
    check(len(rows)==100, 'Manifest must have 100 selections')
    check(len({r['route_id'] for r in rows})==100, 'Duplicate selection IDs')
    check({r['selection_number'] for r in rows}=={str(n) for n in range(1,101)}, 'Invalid selection numbering')
    check(all(r['route_id']==f"co14-{int(r['selection_number']):03d}" for r in rows), 'ID/number mismatch')
    check(all(r['manifest_version']==config['manifest_version'] for r in rows), 'Manifest version mismatch')
    check(hashlib.sha256(raw).hexdigest()==config['manifest_sha256'], 'Manifest changed without updating the versioned freeze')
    check(set(fields)==set(config['manifest_fields']), 'Manifest/schema columns differ')
    check(all(r['canonical_name'] and r['requested_name'] for r in rows), 'Missing original/canonical names')
    required = [r for r in rows if r['required_summit']]
    check(len(required)==58 and len({r['required_summit'] for r in required})==58, 'Required summit coverage must be 58')
    check({r['required_summit'] for r in required}==set(config['required_summits']), 'Required summit roster changed')
    check(Counter(r['selection_group'] for r in rows)==config['selection_group_counts'], 'Selection groups must remain 53/5/42')
    byid = {r['route_id']: r for r in rows}
    for r in rows:
        for field in ['is_replacement','itinerary_verified','dry_summer_verified']:
            check(r[field] in ('true','false'), f"{r['route_id']}: invalid boolean {field}")
        check(r['conditions_scope']=='dry_summer', f"{r['route_id']}: unexpected conditions scope")
        check(r['start_policy'] and r['descent_policy'] and r['summit_order'], f"{r['route_id']}: incomplete itinerary contract")
        check(r['source_review_status'] in config['source_review_statuses'], f"{r['route_id']}: invalid source review status")
        check(bool(r['source_url'] or r['supporting_source_url'] or r['source_component_urls']), f"{r['route_id']}: no source evidence")
        for u in [r['source_url'],r['supporting_source_url']]+r['source_component_urls'].split('|'):
            if not u: continue
            p=urlsplit(u)
            check(p.scheme=='https' and p.hostname=='www.14ers.com' and not p.fragment,
                  f"{r['route_id']}: invalid source URL")
            if u==r['source_url']:
                check(p.path=='/route.php' and bool(parse_qs(p.query).get('route')), f"{r['route_id']}: invalid official route URL")
        if r['yds_class_override']:
            check(r['yds_class_override'] in config['yds_encoding'], f"{r['route_id']}: unsupported YDS class")
            check(bool(r['yds_override_provenance']), f"{r['route_id']}: untracked grade override")
        if r['related_itinerary_group']:
            members=r['related_itinerary_group'].split('|')
            check(r['route_id'] in members and all(i in byid for i in members), f"{r['route_id']}: invalid related group")
            check(all(byid[i]['related_itinerary_group']==r['related_itinerary_group'] for i in members if i in byid), f"{r['route_id']}: asymmetric related group")
    for number,code in config['approved_replacements'].items():
        r=byid[f'co14-{int(number):03d}']
        check(r['is_replacement']=='true' and r['source_url'].endswith('route='+code), f'Replacement #{number} is not the approved route')
    check(len({r['source_url'] for r in rows if r['source_url']})==100, 'Roster must have 100 distinct official source routes')
    check(config['yds_encoding']=={'1':1,'2':2,'3':4,'4':8,'5':16}, 'YDS encoding must be 1/2/4/8/16')
    check('Bierstadt' in byid['co14-097']['canonical_name'] and 'Blue Sky' in byid['co14-097']['canonical_name'], 'Tour de Abyss identity incorrect')
    check(byid['co14-097']['is_replacement']=='false', 'Tour de Abyss must be retained')
    check(config['duplicates']['allowed'] is False, 'Exact route aliases must be excluded')

    # Compare embedded notebook definitions and CSV directly to canonical files.
    notebook=json.loads((out/'01_ingestion_colab.ipynb').read_text())
    cells=[(''.join(c['source']) if isinstance(c['source'],list) else c['source'])
           for c in notebook['cells'] if c['cell_type']=='code']
    source=(out/'block1_scraper.py').read_text()
    definitions=source.split("\nif __name__ == '__main__':")[0]
    check(definitions in cells, 'Notebook scraper definitions are stale')
    manifest_cells=[c for c in cells if c.startswith('MANIFEST_CSV =')]
    if manifest_cells:
        value=ast.literal_eval(ast.parse(manifest_cells[0]).body[0].value)
        check(value==raw.decode('utf-8'), 'Notebook manifest is stale')
    else: check(False, 'Notebook has no embedded manifest')
    if (out/'block2_features.py').exists():
        feature_cells=[c for c in cells if c.startswith('FEATURE_SOURCE =')]
        check(len(feature_cells)==1, 'Notebook must have one synchronized Phase 3 source cell')
        if len(feature_cells)==1:
            embedded=ast.literal_eval(ast.parse(feature_cells[0]).body[0].value)
            check(embedded==(out/'block2_features.py').read_text(), 'Notebook Phase 3 source is stale')
        compile((out/'block2_features.py').read_text(), 'block2_features.py', 'exec')
        feature_contract=config.get('phase3', {})
        check(feature_contract.get('parameters', {}).get('threshold_unit')=='percent_grade',
              'Phase 3 grade units must match latest user request')
        if (out/'phase3_review.json').exists():
            feature_review=json.loads((out/'phase3_review.json').read_text())
            check(feature_review['manifest_sha256']==config['manifest_sha256'], 'Phase 3 review uses stale roster')
            check(feature_review['config_sha256']==hashlib.sha256((out/'project_config.json').read_bytes()).hexdigest(), 'Phase 3 review uses stale config')
            check(feature_review['implementation_sha256']==hashlib.sha256((out/'block2_features.py').read_bytes()).hexdigest(), 'Phase 3 review uses stale implementation')
    if (out/'block3_embeddings.py').exists():
        compile((out/'block3_embeddings.py').read_text(), 'block3_embeddings.py', 'exec')
        analysis=root/'private_data/phase4/analysis.json'
        if analysis.exists():
            saved=json.loads(analysis.read_text())
            for key,path in [('config_sha256',out/'project_config.json'),
                             ('implementation_sha256',out/'block3_embeddings.py'),
                             ('feature_sha256',root/'private_data/routes_features.csv'),
                             ('phase3_review_sha256',out/'phase3_review.json')]:
                check(saved[key]==hashlib.sha256(path.read_bytes()).hexdigest(), f'Phase 4 {key} is stale')
            check(saved['manifest_sha256']==config['manifest_sha256'], 'Phase 4 roster is stale')
            check(saved['cohorts']['observed_segments_100']['count']==100, 'Qualified full-roster view must have 100 routes')
        check(config['phase4']['complete_itinerary_acceptance'] is False,
              'Complete-itinerary acceptance requires reviewed source coverage')
    if (out/'block4_ranker.py').exists():
        compile((out/'block4_ranker.py').read_text(), 'block4_ranker.py', 'exec')
        check(not config['phase5']['final_ranking_acceptance'], 'Synthetic labels cannot establish final ranking acceptance')
        check(not set(config['phase5']['input_features'])&set(config['phase5']['excluded_predictors']), 'Phase 5 predictor leakage')
        saved_path=root/'private_data/phase5/evaluation.json'
        if saved_path.exists():
            saved=json.loads(saved_path.read_text())
            for key,path in [('config_sha256',out/'project_config.json'),
                             ('implementation_sha256',out/'block4_ranker.py'),
                             ('feature_sha256',root/'private_data/routes_features.csv'),
                             ('phase3_review_sha256',out/'phase3_review.json')]:
                check(saved[key]==hashlib.sha256(path.read_bytes()).hexdigest(), f'Phase 5 {key} is stale')
            check(saved['human_comparison_count']==0, 'Human comparisons cannot be synthesized')
            check(len(saved['final_models']['observed_segments_100']['route_ids'])==100, 'Phase 5 missing roster rows')
    if (out/'block5_community.py').exists():
        compile((out/'block5_community.py').read_text(), 'block5_community.py', 'exec')
        review_path=out/'phase6_review.json'
        if review_path.exists():
            saved=json.loads(review_path.read_text())
            for key,path in [('config_sha256',out/'project_config.json'),
                             ('implementation_sha256',out/'block5_community.py'),
                             ('feature_sha256',root/'private_data/routes_features.csv'),
                             ('phase5_model_sha256',root/'private_data/phase5/evaluation.json')]:
                if path.exists():
                    check(saved[key]==hashlib.sha256(path.read_bytes()).hexdigest(), f'Phase 6 {key} is stale')
            check(not saved['human_labels_fabricated'], 'Phase 6 must not fabricate human evidence')
            check(saved['evaluation_pool_size']==990, 'Phase 6 evaluation pool changed')
            check(not saved['live_backend_deployed'], 'Live deployment is not established')
    tree=ast.parse(source)
    encoding=next((ast.literal_eval(node.value) for node in tree.body
                   if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='YDS_ENCODING' for t in node.targets)), None)
    check(encoding=={int(k):v for k,v in config['yds_encoding'].items()}, 'Scraper encoding differs from contract')
    compile(source, 'block1_scraper.py', 'exec')
    for i,cell in enumerate(cells):
        if not cell.startswith('%'): compile(cell,f'notebook_{i}','exec')
    with zipfile.ZipFile(out/'colorado_14er_kickoff.zip') as bundle:
        for name in ['route_manifest.csv','block1_scraper.py','01_ingestion_colab.ipynb','project_roadmap.md','project_config.json']:
            check(bundle.read(name)==(out/name).read_bytes(), f'Bundle member {name} is stale')
        for name in ['README.md','scripts/audit_phase2.py','scripts/validate_project.py',
                     'scripts/sync_deliverables.py','tests/test_block1.py','.gitignore']:
            if (root/name).exists():
                check(bundle.read(name)==(root/name).read_bytes(), f'Bundle member {name} is stale')
        if (out/'phase2_review.json').exists():
            check(bundle.read('phase2_review.json')==(out/'phase2_review.json').read_bytes(), 'Phase 2 bundled review is stale')
        for name in ('block2_features.py', 'phase3_review.json', 'block3_embeddings.py', 'phase4_report.md', 'block4_ranker.py', 'phase5_report.md', 'block5_community.py', 'phase6_report.md', 'phase6_review.json'):
            if (out/name).exists():
                check(bundle.read(name)==(out/name).read_bytes(), f'Phase 3 bundled {name} is stale')
        if (root/'tests/test_block2.py').exists():
            check(bundle.read('tests/test_block2.py')==(root/'tests/test_block2.py').read_bytes(), 'Phase 3 bundled tests are stale')
        if (root/'tests/test_block3.py').exists():
            check(bundle.read('tests/test_block3.py')==(root/'tests/test_block3.py').read_bytes(), 'Phase 4 bundled tests are stale')
        if (root/'tests/test_block4.py').exists():
            check(bundle.read('tests/test_block4.py')==(root/'tests/test_block4.py').read_bytes(), 'Phase 5 bundled tests are stale')
        if (root/'tests/test_block5.py').exists():
            check(bundle.read('tests/test_block5.py')==(root/'tests/test_block5.py').read_bytes(), 'Phase 6 bundled tests are stale')
        check(not any(name.startswith(('private_data/','work/','data/raw/')) for name in bundle.namelist()),
              'Private raw data must not appear in the public bundle')

    access=config['source_access']
    permission_ready=access['permission_status']=='documented' and bool(access['permission_evidence'])
    smoke_ready=access['raw_http_smoke_test']['status']=='passed' and access['raw_http_smoke_test']['live_gpx_download_verified']
    return {
        'contract_checks_passed':not errors,
        'phase1_engineering_status':'defined_and_validated' if not errors else 'validation_failed',
        'phase1_full_acceptance':not errors and permission_ready and smoke_ready and access['download_agreement_accepted'],
        'phase2_bulk_ingestion_started':access['bulk_ingestion_started'],
        'manifest_version':config['manifest_version'],
        'manifest_sha256':hashlib.sha256(raw).hexdigest(),
        'route_selections':len(rows),
        'required_summits':len(required),
        'selection_groups':dict(Counter(r['selection_group'] for r in rows)),
        'official_route_mappings':sum(bool(r['source_url']) for r in rows),
        'curation_selections':[r['route_id'] for r in rows if not r['source_url']],
        'related_itinerary_groups':sorted({r['related_itinerary_group'] for r in rows if r['related_itinerary_group']}),
        'dry_itinerary_verification_pending':sum(r['dry_summer_verified']!='true' or r['itinerary_verified']!='true' for r in rows),
        'external_requirements':[
            'Document source permission covering automated/derived/public use.',
            'Browser GPX acquisition is verified; direct HTTP transport remains optional and historically blocked.',
            'Verify all selected complete dry itineraries; resolve Culebra gain units and North Eolus full-route totals before final features.'
        ],
        'errors':errors,
    }


if __name__=='__main__':
    report=validate()
    path=ROOT/'outputs/phase1_review.json'
    temp=path.with_suffix('.json.tmp')
    temp.write_text(json.dumps(report,indent=2)+'\n')
    temp.replace(path)
    print(json.dumps(report,indent=2))
    raise SystemExit(0 if report['contract_checks_passed'] else 1)
