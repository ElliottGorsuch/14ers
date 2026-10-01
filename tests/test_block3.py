"""Phase Four numerical contracts and local artifact integrity."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('embeddings',ROOT/'outputs/block3_embeddings.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
np=m.np
PARAMS=json.loads((ROOT/'outputs/project_config.json').read_text())['phase4']['parameters']

class Tests(unittest.TestCase):
    def test_scaler_pca_reconstruction_and_biplot_correlations(self):
        rng=np.random.default_rng(123);x=rng.normal(size=(30,5))*np.array([1,3,5,7,11])+np.array([2,3,4,5,6])
        scaler,pca,z,scores,load,sd=m.fit_pca(x)
        np.testing.assert_allclose(z.mean(axis=0),0,atol=1e-12)
        np.testing.assert_allclose(z.std(axis=0),1,atol=1e-12)
        np.testing.assert_allclose(scores@pca.components_,z,atol=1e-10)
        for i in range(5):
            for j in range(2):self.assertAlmostEqual(load[i,j],np.corrcoef(z[:,i],scores[:,j])[0,1])
        np.testing.assert_allclose((scores[:,:2]/sd[:2]).std(axis=0),1,atol=1e-12)
        self.assertTrue((np.abs(load)<=1+1e-12).all())
        self.assertAlmostEqual(pca.explained_variance_ratio_.sum(),1)

    def test_units_do_not_change_standardized_pca(self):
        x=np.random.default_rng(1).normal(size=(20,4))
        a=m.fit_pca(x);b=m.fit_pca(x*np.array([1609.344,3.28084,100,1]))
        np.testing.assert_allclose(a[2],b[2],atol=1e-12)
        np.testing.assert_allclose(a[1].explained_variance_ratio_,b[1].explained_variance_ratio_,atol=1e-12)

    def test_neighbor_identity_and_no_self_neighbor(self):
        x=np.array([[0,0],[1,0],[3,0],[10,0],[20,0],[30,0]],dtype=float)
        self.assertEqual(m.neighbor_agreement(x,x,2),1)
        for i,row in enumerate(m.neighbors(x,2)):self.assertNotIn(i,row)

    def test_seeded_nonlinear_methods_are_real_and_repeatable(self):
        z=np.random.default_rng(31).normal(size=(24,4));params=dict(PARAMS,tsne_max_iter=350)
        with m.threadpool_limits(limits=1):
            for method in ['UMAP','t-SNE']:
                a,setting=m.fit_nonlinear(z,method,params,42)
                b,_=m.fit_nonlinear(z,method,params,42)
                self.assertEqual(a.shape,(24,2));self.assertTrue(np.isfinite(a).all())
                np.testing.assert_allclose(a,b,atol=1e-7)
                if method=='t-SNE':self.assertEqual(setting['init'],'pca')
            _,setting=m.fit_nonlinear(z,'t-SNE',params,43)
            self.assertEqual(setting['init'],'random')

    @unittest.skipUnless((ROOT/'private_data/phase4/analysis.json').exists(),'private analysis unavailable')
    def test_real_data_cohorts_provenance_and_finite_coordinates(self):
        data=json.loads((ROOT/'private_data/phase4/analysis.json').read_text())
        self.assertEqual(data['feature_sha256'],m.sha(ROOT/'private_data/routes_features.csv'))
        self.assertEqual([c['count'] for c in data['cohorts'].values()],[37,96,100,100])
        self.assertEqual(data['cohorts']['numeric_qa_37']['class_counts']['5'],0)
        self.assertEqual(len(data['coverage_cases']),4)
        for c in data['coverage_cases']:
            self.assertLess(float(c['profile_valid_distance_fraction']),.95)
        self.assertEqual(len(data['cohorts']['usable_profiles_96']['features']),11)
        for c in data['cohorts'].values():
            self.assertEqual(len(c['features']),len(c['feature_mean']))
            self.assertFalse(c['constant_features'])
            for method in ['PCA','UMAP','t-SNE']:
                xy=np.array(c[method]['coords']);self.assertEqual(xy.shape,(c['count'],2))
                self.assertTrue(np.isfinite(xy).all())
                self.assertTrue(0<=c[method]['trustworthiness']<=1)
                self.assertTrue(0<=c[method]['mean_neighbor_overlap']<=1)
            self.assertAlmostEqual(sum(c['explained_variance_ratio']),1)
            self.assertEqual(len(c['UMAP']['sensitivity']),4)
            self.assertEqual(len(c['t-SNE']['sensitivity']),4)

    @unittest.skipUnless((ROOT/'private_data/phase4/route_exploration.html').exists(),'private plot page unavailable')
    def test_html_is_offline_and_contains_scope_and_controls(self):
        html=(ROOT/'private_data/phase4/route_exploration.html').read_text()
        self.assertNotIn('<script src=',html)
        for text in ['id="cohort"','id="color"','id="pca"','id="umap"','id="tsne"','Recorded tracks only','const DATA=']:
            self.assertIn(text,html)
        self.assertIn('plotly.js',html)

if __name__=='__main__':unittest.main()
