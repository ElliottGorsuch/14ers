"""Public Route import invariants and fail-closed source reconciliation."""
import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('site_exporter', ROOT/'scripts/update_site_catalog.py')
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)


class SiteManifestTests(unittest.TestCase):
    def fixture(self, root):
        (root/'site_export').mkdir()
        (root/'outputs').mkdir()
        entries = []
        rows = []
        for rid, peaks in [('co14-066', ['Mt. Democrat','Mt. Cameron','Mt. Lincoln','Mt. Bross']),
                           ('co14-107', ['Mt. Democrat'])]:
            entry = dict(route_id=rid, canonical_name=rid, primary_peak=peaks[0], summits=peaks,
                         source_url='', source_kind='unverified_request', identity_status='pending',
                         catalog_status='pending_measurements', geometry_scope='unavailable',
                         complete_itinerary_verified=False, plot_ready=False, rank_ready=False,
                         voting_ready=False, recorded_start={'lat':1,'lon':2}, similar_routes=[])
            entries.append(entry)
            rows.append(dict(route_id=rid, feature_version='3.1.0', yds_class='',
                             **{f:'' for f in ['pca_x','pca_y','umap_x','umap_y','tsne_x','tsne_y',
                                              'provisional_rank','provisional_score']}))
        with (root/'site_export/route_features_full.csv').open('w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
        catalog = dict(routes=entries, active_count=2, retired_ids=['co14-069'], catalog_version='2.0.0')
        (root/'site_export/route_catalog.json').write_text(json.dumps(catalog))
        return catalog

    def test_public_projection_excludes_private_fields_and_keeps_unknown_null(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); self.fixture(root)
            result = exporter.export_public_manifest(root)
            records = json.loads((root/'outputs/site_route_manifest.json').read_text())
            self.assertEqual(result['routes'], 2)
            self.assertIsNone(records[1]['yds_class'])
            self.assertNotIn('recorded_start', records[0])
            self.assertNotIn('similar_routes', records[0])
            self.assertNotIn('provisional_score', records[0])

    def test_mismatched_ids_readiness_and_retirements_rejected_before_write(self):
        for change in ('ids','readiness','retired','peak'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temp:
                root = Path(temp); catalog = self.fixture(root)
                if change == 'ids': catalog['routes'][1]['route_id'] = 'co14-108'
                if change == 'readiness': catalog['routes'][1]['plot_ready'] = True
                if change == 'retired': catalog['retired_ids'].append('co14-107')
                if change == 'peak': catalog['routes'][1]['summits'].append('Mt. Lincoln')
                (root/'site_export/route_catalog.json').write_text(json.dumps(catalog))
                with self.assertRaises(ValueError): exporter.export_public_manifest(root)
                self.assertFalse((root/'outputs/site_route_manifest.json').exists())

    def test_published_manifest_contract(self):
        records = json.loads((ROOT/'outputs/site_route_manifest.json').read_text())
        ids = [r['route_id'] for r in records]
        self.assertEqual(len(ids), 109)
        self.assertEqual(len(set(ids)), 109)
        self.assertFalse(set(ids) & {'co14-008','co14-054','co14-069'})
        self.assertEqual(sum(r['plot_ready'] for r in records), 103)
        self.assertEqual(sum(r['rank_ready'] for r in records), 103)
        self.assertFalse(any(r['voting_ready'] for r in records))
        for peak in ['Mt. Cameron','Mt. Lincoln']:
            self.assertEqual([r['route_id'] for r in records if peak in r['summits']], ['co14-066'])
        self.assertEqual([r['route_id'] for r in records if r['identity_status']=='pending'], ['co14-107'])


if __name__ == '__main__':
    unittest.main()
