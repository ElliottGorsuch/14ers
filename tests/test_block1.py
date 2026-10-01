import importlib.util
import json
import tempfile
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.robotparser import RobotFileParser

spec = importlib.util.spec_from_file_location('scraper', 'outputs/block1_scraper.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
audit_spec=importlib.util.spec_from_file_location('audit','scripts/validate_project.py')
audit=importlib.util.module_from_spec(audit_spec)
audit_spec.loader.exec_module(audit)

PAGE = b'''<html><h1>Mount Elbert Northeast Ridge</h1>
<nav>Route Description Maps</nav><p>Difficulty Class 1</p>
<p>Exposure Low Rockfall Potential Low Route-Finding Low Commitment Low</p>
<p>Elevation Gain 4,500 ft Length Round-Trip RT 9.75 mi</p>
<a href="/downloads/elbert.gpx">GPX</a><p>Route Last Updated: Aug 2026</p></html>'''
GPX = b'''<?xml version="1.0"?><gpx xmlns="http://www.topografix.com/GPX/1/1">
<trk><trkseg><trkpt lat="39.1" lon="-106.4"><ele>3000</ele></trkpt>
<trkpt lat="39.101" lon="-106.401"><ele>3010</ele></trkpt></trkseg></trk></gpx>'''


class Response:
    def __init__(self, status=200, body=PAGE, headers=None):
        self.status_code, self.body, self.headers = status, body, headers or {}
        self.text = body.decode()
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def iter_content(self, *args): yield self.body


class Tests(unittest.TestCase):
    def test_real_overview_footer_is_not_a_start_label(self):
        page=PAGE.replace(b'9.75 mi</p>',b'9.75 mi Peak Conditions 803 reports Downloads</p>')
        parsed=m.parse_route(page,m.BASE+'route.php?route=elbe1')
        self.assertEqual(parsed['source_distance_mi_candidates'],[{'value':9.75,'start_label':''}])
        selected=m.apply_selection_metadata({'start_name':'Mt. Elbert North'},parsed)
        self.assertEqual(selected['source_distance_mi'],9.75)

    def test_browser_receipts_preserve_unreviewed_scope_and_reject_tamper(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d); folder=base/'browser'; folder.mkdir()
            (folder/'elbe1.gpx').write_bytes(GPX)
            (folder/'elbe1_metadata.html').write_bytes(PAGE)
            receipt={'code':'elbe1', 'url':m.BASE+'route.php?route=elbe1',
                     'method':'normal_browser_GPX_control', 'downloaded_at':'2026-09-30T21:00:00Z',
                     'agreement':'user_approved_displayed_terms_2026-09-30',
                     'gpx_sha256':m.hashlib.sha256(GPX).hexdigest(),
                     'metadata_sha256':m.hashlib.sha256(PAGE).hexdigest()}
            m.write_json(folder/'download_ledger.json',[receipt])
            with patch.object(m.Client,'check_robots',side_effect=AssertionError('offline network')):
                summary=m.run('outputs/route_manifest.csv',base/'raw','fixture',offline=True,
                              browser_download_dir=folder,download_agreement_accepted=True)
            self.assertEqual(summary['downloaded'],1)
            self.assertEqual(summary['training_eligible'],0)
            self.assertEqual(summary['requested'],100)
            (folder/'elbe1.gpx').write_bytes(GPX+b' ')
            with self.assertRaises(m.IngestionError):
                m.run('outputs/route_manifest.csv',base/'other','fixture',offline=True,browser_download_dir=folder)

    def curated_fixture(self, row):
        record = {k: row[k] for k in ('route_id','summit_order','start_policy','descent_policy')}
        record.update(reviewer='Fixture reviewer', review_date='2026-09-30',
                      metadata_evidence='Synthetic test only', geometry_evidence='Synthetic test only',
                      conditions_evidence='Synthetic test only', source_references=[m.BASE+'route.php?route=elbe1'],
                      start_name=row.get('start_name') or 'Fixture trailhead',
                      yds_raw='Class 5.4', yds_class=5, source_distance_mi=9.75, source_gain_ft=4500,
                      exposure_raw='High', rockfall_raw='Moderate', route_finding_raw='Considerable',
                      commitment_raw='High', gpx_file='fixture.gpx',
                      gpx_sha256=m.hashlib.sha256(GPX).hexdigest(),
                      itinerary_verified=True, dry_summer_verified=True)
        return record

    def test_multiple_start_totals_are_not_first_number_wins(self):
        page=PAGE.replace(b'Elevation Gain 4,500 ft Length Round-Trip RT 9.75 mi',
            b'Elevation Gain 3,150 ft From Upper gate 4,250 ft From Rockdale 2WD '
            b'Length Round-Trip RT 5.75 mi From Upper gate 11.75 mi From Rockdale 2WD')
        source=m.parse_route(page,m.BASE+'route.php?route=miss2')
        self.assertIsNone(source['source_distance_mi'])
        row={'start_name':'Rockdale 2WD'}
        matched=m.apply_selection_metadata(row,source)
        self.assertEqual((matched['source_distance_mi'],matched['source_gain_ft']),(11.75,4250))
        uncertain=m.apply_selection_metadata({'start_name':'Unknown lower trailhead'},source)
        self.assertIsNone(uncertain['source_distance_mi'])
        self.assertEqual(uncertain['metadata_scope_status'],'review_required')

    def test_prefix_and_suffix_start_totals_preserve_access_qualifiers(self):
        source=m.parse_route(PAGE.replace(b'Elevation Gain 4,500 ft Length Round-Trip RT 9.75 mi',
            b'Elevation Gain From 4WD TH: 3,000 feet From 2WD TH: 5,500 feet '
            b'Length Round-Trip RT From 4WD TH: 7.50 miles From 2WD TH: 15.50 miles'),m.BASE+'route.php?route=unco1')
        result=m.apply_selection_metadata({'start_name':'2WD TH'},source)
        self.assertEqual((result['source_distance_mi'],result['source_gain_ft']),(15.5,5500))
        self.assertNotEqual(m.start_norm('Rockdale (2WD)'),m.start_norm('Rockdale (4WD)'))
        source=m.parse_route(PAGE.replace(b'Elevation Gain 4,500 ft Length Round-Trip RT 9.75 mi',
            b'Elevation Gain 4,250 feet - starting at Rockdale (2WD) 3,150 feet - starting at the gate (4WD) '
            b'Length Round-Trip RT 11.75 miles - starting at Rockdale (2WD) 5.75 miles - starting at the gate (4WD)'),m.BASE+'route.php?route=miss2')
        result=m.apply_selection_metadata({'start_name':'Rockdale 2WD'},source)
        self.assertEqual((result['source_distance_mi'],result['source_gain_ft']),(11.75,4250))

    def test_effective_grade_preserves_raw_evidence(self):
        source=m.parse_route(PAGE,m.BASE+'route.php?route=elbe1')
        row={'yds_class_override':'5','yds_override_provenance':'reviewed user decision'}
        selected=m.apply_selection_metadata(row,source)
        self.assertEqual(selected['yds_raw'],'Class 1')
        self.assertEqual(selected['yds_observed_class'],1)
        self.assertEqual(selected['yds_encoded'],16)
        self.assertEqual(source['yds_class'],1)

    def test_approved_export_offline_and_audit_tamper(self):
        audit2_spec=importlib.util.spec_from_file_location('audit2','scripts/audit_phase2.py')
        audit2=importlib.util.module_from_spec(audit2_spec)
        audit2_spec.loader.exec_module(audit2)
        with tempfile.TemporaryDirectory() as d:
            base=Path(d)
            rows=m.load_manifest('outputs/route_manifest.csv')
            (base/'fixture.gpx').write_bytes(GPX)
            doc={'schema_version':'1.0.0', 'manifest_sha256':m.hashlib.sha256(Path('outputs/route_manifest.csv').read_bytes()).hexdigest(),
                 'permission_evidence':'Synthetic local test permission', 'records':[self.curated_fixture(rows[68])]}
            export=base/'approved.json';m.write_json(export,doc)
            with patch.object(m.Client,'check_robots',side_effect=AssertionError('offline network')):
                report=m.run('outputs/route_manifest.csv',base/'raw','fixture',curated_file=export,offline=True)
            self.assertEqual(report['downloaded'],1)
            self.assertEqual(report['training_eligible'],1)
            result=audit2.audit(base/'raw')
            self.assertTrue(result['snapshot_integrity_passed'],result['errors'])
            self.assertFalse(result['phase3_dataset_ready'])
            (base/'raw/gpx/co14-069.gpx').write_bytes(GPX+b' ')
            self.assertFalse(audit2.audit(base/'raw')['snapshot_integrity_passed'])

    def test_curated_rejects_missing_evidence_wrong_hash_and_path(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);(base/'fixture.gpx').write_bytes(GPX)
            row=m.load_manifest('outputs/route_manifest.csv')[68]
            record=self.curated_fixture(row)
            doc={'permission_evidence':'Synthetic test'}
            for changes in ({'gpx_sha256':'bad'}, {'gpx_file':'../fixture.gpx'},
                            {'conditions_evidence':''}, {'source_gain_ft':True},
                            {'summit_order':'Wrong peak'}, {'dry_summer_verified':'true'}):
                with self.assertRaises(m.IngestionError):
                    m.ingest_curated(dict(row),{**record,**changes},doc,base/'approved.json',base/'raw')

    def test_smoke_subset_fetches_only_selected_source_pages(self):
        source=m.parse_route(PAGE,m.BASE+'route.php?route=elbe1')
        with tempfile.TemporaryDirectory() as d, patch.object(m.Client,'check_robots'), \
                patch.object(m,'discover',side_effect=AssertionError('Full index crawl')), \
                patch.object(m.Client,'fetch',side_effect=[PAGE,GPX]) as fetch:
            report=m.run('outputs/route_manifest.csv',d,'fixture',True,True,only_routes=['co14-001'])
            self.assertEqual(fetch.call_count,2)
            self.assertEqual(report['statuses'],{'not_selected':99,'downloaded':1})
            self.assertEqual(report['training_eligible'],0)

    def test_single_labeled_wrong_start_is_withheld(self):
        page=PAGE.replace(b'4,500 ft Length',b'4,500 ft From Upper gate Length')
        source=m.parse_route(page,m.BASE+'route.php?route=elbe1')
        selected=m.apply_selection_metadata({'start_name':'Lower trailhead'},source)
        self.assertIsNone(selected['source_gain_ft'])

    def test_manifest_exact(self):
        rows = m.load_manifest('outputs/route_manifest.csv')
        self.assertEqual(len(rows), 100)
        self.assertIn('Tour de Abyss', rows[96]['canonical_name'])

    def test_phase1_replacements_and_originals(self):
        rows=m.load_manifest('outputs/route_manifest.csv')
        self.assertEqual(rows[84]['requested_name'],'Mt. Sherman - East Ridge')
        self.assertEqual(rows[84]['source_url'],m.BASE+'route.php?route=sher2')
        self.assertEqual(rows[86]['requested_name'],'Missouri Mountain - North Face')
        self.assertEqual(rows[86]['source_url'],m.BASE+'route.php?route=miss2')
        self.assertEqual(rows[94]['requested_name'],'Uncompahgre Peak - East Ridge')
        self.assertEqual(rows[94]['source_url'],m.BASE+'route.php?route=kitc4')
        self.assertEqual(rows[68]['source_url'],m.BASE+'route.php?route=cnee5')
        self.assertEqual(rows[68]['yds_class_override'],'')
        self.assertEqual(rows[96]['is_replacement'],'false')
        self.assertEqual(len({r['required_summit'] for r in rows if r['required_summit']}),58)

    def test_phase1_contract_and_bundle(self):
        report=audit.validate()
        self.assertTrue(report['contract_checks_passed'],report['errors'])
        self.assertEqual(report['official_route_mappings'],100)
        self.assertFalse(report['phase1_full_acceptance'])
        self.assertEqual(report['curation_selections'],[])

    def test_unreviewed_manifest_edit_is_detected(self):
        with tempfile.TemporaryDirectory() as d:
            shutil.copytree('outputs',Path(d)/'outputs')
            p=Path(d)/'outputs/route_manifest.csv'
            p.write_text(p.read_text().replace('Rockdale 2WD','Upper gate',1))
            report=audit.validate(d)
            self.assertFalse(report['contract_checks_passed'])
            self.assertTrue(any('freeze' in e for e in report['errors']))

    def test_transitive_related_source_groups(self):
        rows=m.load_manifest('outputs/route_manifest.csv')
        for r in rows:
            r.update(status='pending',source_url='',related_itinerary_group='')
        rows[0]['related_itinerary_group']='co14-001|co14-002'
        rows[1]['related_itinerary_group']='co14-001|co14-002'
        rows[1]['source_url']=rows[2]['source_url']=m.BASE+'route.php?route=elbe1'
        with tempfile.TemporaryDirectory() as d:
            m.export(d,rows,[])
            saved=m.pd.read_csv(Path(d)/'route_status.csv',keep_default_na=False)
            self.assertEqual(list(saved.evaluation_group[:3]),['co14-001|co14-002|co14-003']*3)
            self.assertEqual(saved.evaluation_group[3],'co14-004')

    def test_metadata_and_links(self):
        r = m.parse_route(PAGE, m.BASE + 'route.php?route=elbe1')
        self.assertEqual(r['source_gain_ft'], 4500)
        self.assertEqual(r['source_distance_mi'], 9.75)
        self.assertEqual(r['yds_encoded'], 1)
        self.assertEqual(r['rockfall_raw'], 'Low')
        self.assertEqual(r['gpx_candidates'], [m.BASE+'downloads/elbert.gpx'])
        self.assertEqual(m.choose({'requested_name':'Mt. Elbert - Northeast Ridge'}, [r])[0], r)
        self.assertIsNone(m.choose({'requested_name':'Mt. Elbert - East Ridge'}, [r])[0])
        self.assertIsNone(m.choose({'requested_name':r['source_title']}, [r,r])[0])

    def test_inline_js_and_snow_class5(self):
        page = PAGE.replace(b'href="/downloads/elbert.gpx"',
                            b'onclick="window.open(\'/download.php?file=abc&amp;type=gpx\')"')
        r = m.parse_route(page, m.BASE+'route.php?route=elbe1')
        self.assertEqual(r['gpx_candidates'], [m.BASE+'download.php?file=abc&type=gpx'])
        snow = PAGE.replace(b'<h1>', b'<h1><img alt="Snow-Only Climb">')
        self.assertTrue(m.parse_route(snow, m.BASE)['snow_only'])
        class5 = PAGE.replace(b'Class 1', b'Class 5.4')
        r = m.parse_route(class5, m.BASE)
        self.assertEqual(r['yds_raw'], 'Class 5.4')
        self.assertEqual(r['yds_encoded'], 16)

    def test_gpx_rejects_and_boundaries(self):
        r = m.validate_gpx(GPX)
        self.assertEqual(r['point_count'], 2)
        self.assertEqual(r['elevation_coverage'], 1)
        with self.assertRaises(m.IngestionError): m.validate_gpx(PAGE)
        with self.assertRaises(m.IngestionError): m.validate_gpx(b'<gpx><wpt lat="39" lon="-106"/></gpx>')
        with self.assertRaises(m.IngestionError): m.validate_gpx(GPX.replace(b'39.1', b'0.1'))
        different_time = GPX.replace(b'</ele>', b'</ele><time>2020-01-01T00:00:00Z</time>')
        self.assertEqual(r['geometry_sha256'], m.validate_gpx(different_time)['geometry_sha256'])

    def test_http_cache_retry_and_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            c = m.Client(d, 'test@example.org')
            c.robots = RobotFileParser(); c.robots.parse(['User-agent: *','Allow: /'])
            c.wait = lambda: None
            with patch.object(c.session, 'get', side_effect=[Response(429, headers={'Retry-After':'1'}),Response(body=GPX)]) as get, patch.object(m.time, 'sleep'):
                self.assertEqual(c.fetch(m.BASE+'a.gpx'), GPX)
                self.assertEqual(get.call_count, 2)
                self.assertEqual(c.fetch(m.BASE+'a.gpx'), GPX)
                self.assertEqual(get.call_count, 2)
            with patch.object(c.session, 'get', return_value=Response(403)) as get:
                with self.assertRaises(m.AccessBlocked): c.fetch(m.BASE+'b.gpx')
                self.assertEqual(get.call_count, 1)
            with patch.object(c.session, 'get', return_value=Response(302, headers={'Location':'https://example.org/a'})):
                with self.assertRaises(m.IngestionError): c.fetch(m.BASE+'c.gpx')
            c.robots = RobotFileParser()
            c.robots.parse(['User-agent: *','Disallow: /'])
            with self.assertRaises(m.IngestionError): c.fetch(m.BASE+'a.gpx')

    def test_run_reports_all_100_when_blocked(self):
        with tempfile.TemporaryDirectory() as d, patch.object(m.Client,'check_robots',side_effect=m.AccessBlocked('HTTP 403')):
            report = m.run('outputs/route_manifest.csv',d,'test@example.org',True,True)
            self.assertEqual(report['statuses'], {'blocked_or_not_attempted':100})
            self.assertFalse(report['complete_100_unique_dry_routes'])
            self.assertEqual(len(m.pd.read_csv(Path(d)/'route_status.csv')),100)

    def test_fixture_end_to_end_and_duplicates(self):
        source = m.parse_route(PAGE,m.BASE+'route.php?route=elbe1')
        with tempfile.TemporaryDirectory() as d:
            rows = m.load_manifest('outputs/route_manifest.csv')
            for r in rows:
                r['source_url'] = ''
                r['canonical_name'] = r['requested_name']
            for r in rows[:2]:
                r['source_url'] = source['source_url']
                r['dry_summer_verified'] = 'true'
                r['itinerary_verified'] = 'true'
            manifest = Path(d)/'manifest.csv'
            m.pd.DataFrame(rows).to_csv(manifest,index=False)
            with patch.object(m.Client,'check_robots'), patch.object(m,'discover',return_value=[source]), patch.object(m.Client,'fetch',return_value=GPX):
                report = m.run(manifest,Path(d)/'raw','test@example.org',True,True)
            self.assertEqual(report['downloaded'],2)
            self.assertEqual(report['training_eligible'],2)
            self.assertEqual(report['duplicate_geometry_groups'],[['co14-001','co14-002']])


if __name__ == '__main__': unittest.main()
