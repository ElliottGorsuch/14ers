"""Refresh existing notebook/bundle from canonical files; never edit copies by hand."""
import json
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs'


def sync():
    config=json.loads((OUT/'project_config.json').read_text())
    path=OUT/'01_ingestion_colab.ipynb'
    nb=json.loads(path.read_text())
    source=(OUT/'block1_scraper.py').read_text().split("\nif __name__ == '__main__':")[0]
    manifest=(OUT/'route_manifest.csv').read_text()
    def get(cell): return ''.join(cell['source']) if isinstance(cell['source'],list) else cell['source']
    for cell in nb['cells']:
        text=get(cell)
        if cell['cell_type']=='code' and text.startswith('"""Colorado 14er ingestion'):
            text=source
        elif cell['cell_type']=='code' and text.startswith('MANIFEST_CSV ='):
            tail=text[text.index('MANIFEST_PATH ='):]
            text='MANIFEST_CSV = '+repr(manifest)+'\n'+tail
        elif cell['cell_type']=='code' and text.startswith('CONTACT ='):
            text='''CONTACT = 'replace-with-your-research-contact-or-project-url'
SOURCE_PERMISSION_CONFIRMED = False
DOWNLOAD_AGREEMENT_ACCEPTED = False
COOKIE_FILE = None
REFRESH = False
CURATED_FILE = None  # Private approved-export JSON; see README.md.
BROWSER_DOWNLOAD_DIR = None  # Private normal-browser GPX/metadata and hashed receipts; OFFLINE=True.
OFFLINE = False  # True imports local exports without making network requests.
ONLY_ROUTES = None  # Smoke test: ['co14-001', 'co14-095', 'co14-097']

if SOURCE_PERMISSION_CONFIRMED and CONTACT.startswith('replace-'):
    raise ValueError('Set CONTACT to your real research contact or project URL.')

summary = run(
    manifest=MANIFEST_PATH,
    out=Path(DATA_ROOT) / 'raw',
    contact=CONTACT,
    source_permission_confirmed=SOURCE_PERMISSION_CONFIRMED,
    download_agreement_accepted=DOWNLOAD_AGREEMENT_ACCEPTED,
    cookie_file=COOKIE_FILE,
    refresh=REFRESH,
    curated_file=CURATED_FILE,
    offline=OFFLINE,
    only_routes=ONLY_ROUTES,
    browser_download_dir=BROWSER_DOWNLOAD_DIR,
)
print(json.dumps(summary, indent=2))
status = pd.read_csv(Path(DATA_ROOT) / 'raw' / 'route_status.csv', keep_default_na=False)
display(status[['route_id', 'canonical_name', 'status', 'metadata_scope_status', 'error']]
        if 'metadata_scope_status' in status else status[['route_id', 'canonical_name', 'status', 'error']])
'''
        elif cell['cell_type']=='markdown':
            if text.startswith('## Execution configuration'):
                text='''## Execution configuration

For live access, set the confirmations only after documented source permission and accepted download agreement; use your own private authorized cookies if needed. Begin with `ONLY_ROUTES = ['co14-001', 'co14-095', 'co14-097']`, inspect the raw HTML/GPX, then collect the full roster. No automated login or verification bypass is implemented.

For an owner-approved local export, set `CURATED_FILE` to its private JSON path and `OFFLINE=True`. The export must carry permission evidence, the matching manifest hash, reviewed metadata/scope and GPX checksums; see README.md for the contract. Offline mode makes no network requests and does not require live-download flags.

To import already accepted normal browser downloads, set `BROWSER_DOWNLOAD_DIR` to the private receipt directory and `OFFLINE=True`, leaving `CURATED_FILE=None`. Hashes and source identity are validated, but scope verification flags remain unchanged. Original ascent tracks are not automatically complete itineraries.

The default flags remain false. Reports preserve all 100 IDs, including pending and smoke-subset rows. Software fixture tests do not establish a complete dataset.'''
            if text.startswith('## Exact requested manifest'):
                text=f'''## Exact requested manifest

The embedded version {config["manifest_version"]} roster contains the 100 approved distinct official routes while preserving every original requested name. The canonical CSV is authoritative. This cell preserves an existing manifest so reruns do not erase reviewed mappings.

Official identities are mapped for all 100 distinct selections. Kiener's, Princeton Southwest Ridge, the custom Chicago Basin combination and six exact-source aliases have been replaced. Original requested labels remain as history; canonical names define the active cohort. A source URL must be an observed `route.php?route=...` URL; participant evidence and component URLs have their own fields.

Set `dry_summer_verified` and `itinerary_verified` only after reviewing complete geometry and conditions. Source identity verification alone does not establish either flag. Update the manifest version and reviewed hash in the project contract when changing the roster or scope.'''
            text=text.replace('the list contains scope conflicts and possible duplicate itineraries',
                              'the updated 100-selection manifest includes four approved replacements, Class 5 = 16, and retained related itineraries')
            text=text.replace('For #97, correct the itinerary identity before assigning a source URL. For #87, select an approved dry-summer replacement. Keep stable route IDs and document those corrections.',
                              '#97 is retained as the Bierstadt–Blue Sky Tour de Abyss. #87 is Missouri West Ridge, #85 is Sherman West Slopes, and #95 is Kit Carson North Ridge. Class 5 encodes as 16. Keep stable IDs and document future changes in project_config.json and the roadmap.')
            text=text.replace('The list contains scope conflicts and possible duplicate itineraries.',
                              'The manifest contains approved replacements and related itineraries retained by user instruction.')
        cell['source']=text.splitlines(keepends=True)
        if cell['cell_type']=='code':
            cell['outputs']=[];cell['execution_count']=None
    # Keep Phase 3 in the existing handoff notebook, with no stale duplicate cells.
    nb['cells'] = [c for c in nb['cells'] if not c.get('metadata', {}).get('phase3_handoff')]
    feature_source = OUT/'block2_features.py'
    if feature_source.exists():
        additions = [
            ('markdown', '''## Phase 3 — recorded-track features and QA

Use percent grade: medium 20–35%, extreme >35%. Block 2 computes steep mileage, longest continuous steep runs, all five source encodings, sensitivity and approximate overlap groups. Complete-itinerary geometry fields remain empty until scope and QA pass. Version 3.1 adds accepted-segment density observations for all 100 tracks with separate recorded-chord bounds; strict densities below 95% valid distance remain missing. Phase Four local exploration and Phase Five preparation are documented in the README/roadmap.

Extract the current kickoff ZIP to a project directory and set `FEATURE_PROJECT_ROOT` below. The package includes the project config, Block 1/2 and snapshot auditor. Keep the already acquired private snapshot at `DATA_ROOT/raw`; the ZIP contains no private GPX. This cell does not assemble or certify missing approaches/returns. Feature dictionaries and parameter choices live in the package's project config.
'''),
            ('code', 'FEATURE_SOURCE = '+repr(feature_source.read_text())+'\n'),
            ('code', '''FEATURE_PROJECT_ROOT = Path('/content/colorado_14er_kickoff')  # Extracted current ZIP; edit if needed.
FEATURE_ARTIFACT_ROOT = FEATURE_PROJECT_ROOT / 'outputs' if (FEATURE_PROJECT_ROOT / 'outputs' / 'project_config.json').exists() else FEATURE_PROJECT_ROOT
if not (FEATURE_ARTIFACT_ROOT / 'project_config.json').exists():
    raise FileNotFoundError('Extract the current kickoff ZIP and set FEATURE_PROJECT_ROOT.')

feature_namespace = {'__name__': 'phase3_notebook'}
exec(compile(FEATURE_SOURCE, 'block2_features.py', 'exec'), feature_namespace)
if feature_namespace['digest'](FEATURE_ARTIFACT_ROOT / 'block2_features.py') != hashlib.sha256(FEATURE_SOURCE.encode()).hexdigest():
    raise ValueError('Notebook and extracted Block 2 differ; use the same synchronized package.')
feature_review = feature_namespace['run_features'](
    FEATURE_PROJECT_ROOT,
    Path(DATA_ROOT) / 'raw',
    Path(DATA_ROOT) / 'routes_features.csv',
    Path(DATA_ROOT) / 'phase3_review.json',
)
print(json.dumps({k: feature_review[k] for k in ('route_count', 'recorded_profiles_computed',
      'profile_qa_pass_count', 'feature_eligible_count', 'phase3_dataset_ready')}, indent=2))
display(pd.read_csv(Path(DATA_ROOT) / 'routes_features.csv', keep_default_na=False)[[
    'route_id', 'canonical_name', 'source_track_crux_density_medium',
    'source_track_crux_density_extreme', 'source_track_steep_above20_mi',
    'source_track_longest_extreme_mi', 'feature_eligible', 'qa_flags']])
''')]
        for index, (kind, text) in enumerate(additions):
            cell = {'cell_type': kind, 'id': f'phase3-{index}', 'metadata': {'phase3_handoff': True},
                    'source': text.splitlines(keepends=True)}
            if kind == 'code':
                cell.update(outputs=[], execution_count=None)
            nb['cells'].append(cell)
        for cell in nb['cells']:
            if cell['cell_type']=='code' and get(cell).startswith('%pip install'):
                cell['source']=['%pip install -q requests beautifulsoup4 pandas defusedxml numpy\n']
    temp=path.with_suffix('.ipynb.tmp')
    temp.write_text(json.dumps(nb,indent=1,ensure_ascii=False)+'\n')
    temp.replace(path)
    archive=OUT/'colorado_14er_kickoff.zip'
    temp=archive.with_suffix('.zip.tmp')
    with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as z:
        for name in ['01_ingestion_colab.ipynb','block1_scraper.py','route_manifest.csv',
                     'project_roadmap.md','project_config.json']:
            z.write(OUT/name,name)
        for name in ['scripts/validate_project.py','scripts/sync_deliverables.py','scripts/audit_phase2.py',
                     'tests/test_block1.py','.gitignore','README.md']:
            z.write(ROOT/name,name)
        if (OUT/'phase1_review.json').exists():
            z.write(OUT/'phase1_review.json','phase1_review.json')
        if (OUT/'phase2_review.json').exists():
            z.write(OUT/'phase2_review.json','phase2_review.json')
        for name in ('block2_features.py', 'phase3_review.json', 'block3_embeddings.py', 'phase4_report.md', 'block4_ranker.py', 'phase5_report.md', 'block5_community.py', 'phase6_report.md', 'phase6_review.json'):
            if (OUT/name).exists():
                z.write(OUT/name, name)
        if (ROOT/'tests/test_block2.py').exists():
            z.write(ROOT/'tests/test_block2.py', 'tests/test_block2.py')
        if (ROOT/'tests/test_block3.py').exists():
            z.write(ROOT/'tests/test_block3.py', 'tests/test_block3.py')
        if (ROOT/'tests/test_block4.py').exists():
            z.write(ROOT/'tests/test_block4.py', 'tests/test_block4.py')
        if (ROOT/'tests/test_block5.py').exists():
            z.write(ROOT/'tests/test_block5.py', 'tests/test_block5.py')
    temp.replace(archive)


if __name__=='__main__':
    sync()
    print('Existing notebook and bundle refreshed from authoritative files.')
