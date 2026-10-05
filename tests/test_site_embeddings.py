"""Scientific and frontend contracts for the frozen-fit interpretation export."""
import csv
import io
import importlib.util
import json
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('site_embeddings',ROOT/'scripts/build_site_embeddings.py')
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
np=s.np

class SiteEmbeddingTests(unittest.TestCase):
    def setUp(self):
        self.data=json.loads((ROOT/'outputs/site_embeddings.json').read_text())

    def test_public_bundle_coverage_and_neighbors(self):
        d=self.data; ids={r['route_id'] for r in d['routes']}
        manifest=json.loads((ROOT/'outputs/site_route_manifest.json').read_text())
        self.assertEqual(d['counts'],{'catalog':109,'embedded':103,'ranked':108})
        self.assertEqual(len(ids),103)
        self.assertEqual(ids | {r['route_id'] for r in d['pending']},{r['route_id'] for r in manifest})
        self.assertEqual(sum(c['size'] for c in d['clusters']),103)
        self.assertEqual(d['pending'][0].keys(),{'route_id','label','reason'})
        for r in d['routes']:
            self.assertEqual(len(r['neighbors']),5)
            self.assertNotIn(r['route_id'],[v['route_id'] for v in r['neighbors']])
            self.assertTrue(set(v['route_id'] for v in r['neighbors'])<=ids)
            self.assertTrue(0<=r['pca_representation']<=1)
            for method,xy in r['coordinates'].items():
                for axis,value in zip(['x','y'],xy):
                    self.assertTrue(d['methods'][method]['domain'][axis][0]<value<d['methods'][method]['domain'][axis][1])
        self.assertAlmostEqual(sum(d['pca']['full_scree_ratio']),1)

    @unittest.skipUnless((ROOT/'private_data/site_export_analysis.json').exists(),'private source not available')
    def test_exact_biplot_and_saved_coordinates(self):
        a=json.loads((ROOT/'private_data/site_export_analysis.json').read_text())
        rows={r['route_id']:r for r in csv.DictReader(io.StringIO((ROOT/'site_export/route_features_full.csv').read_text()))}
        x=np.array([[s.RISKS[rows[rid][f]] if f in s.FIELDS[5:9] else float(rows[rid][f]) for f in s.FIELDS] for rid in a['embedding_cohort_ids']])
        z=(x-np.array(a['feature_mean']))/np.array(a['feature_scale'])
        t=np.array([r['coordinates']['pca'] for r in self.data['routes']])
        f=np.array([r['biplot'] for r in self.data['routes']])
        c=np.array([r['arrow'] for r in self.data['features']])
        np.testing.assert_allclose(t,a['coordinates']['pca'],atol=1e-12)
        np.testing.assert_allclose(f@c.T,t@np.array(a['pca_components']),atol=1e-10)
        for i in range(11):
            for j in range(2):
                self.assertAlmostEqual(c[i,j],np.corrcoef(z[:,i],t[:,j])[0,1])
        self.assertEqual(self.data['source_feature_sha256'],s.m.sha(ROOT/'site_export/route_features_full.csv'))

if __name__=='__main__':unittest.main()
