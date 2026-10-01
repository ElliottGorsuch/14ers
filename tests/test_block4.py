"""Phase Five analytic gradient, pair semantics, group leakage and saved-model tests."""
import csv
import importlib.util
import json
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('ranker',ROOT/'outputs/block4_ranker.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
np=m.np
SETTINGS=json.loads((ROOT/'outputs/project_config.json').read_text())['phase5']

class Tests(unittest.TestCase):
    def test_pair_orientation_unique_and_reversal(self):
        ij=m.pairs(5);self.assertEqual(len(ij),10);self.assertTrue((ij[:,0]<ij[:,1]).all())
        s=np.array([1.,0.,-1.]);y=m.expit(s[m.pairs(3)[:,0]]-s[m.pairs(3)[:,1]])
        self.assertAlmostEqual(m.pair_loss(s,m.pairs(3),y),m.pair_loss(-s,m.pairs(3),1-y))

    def test_linear_gradient_matches_finite_difference(self):
        z=np.random.default_rng(1).normal(size=(7,3));ij=m.pairs(7);y=np.linspace(.2,.8,len(ij));w=np.array([.2,-.1,.3]);_,grad=m.linear_objective(w,z,ij,y,.02)
        for j in range(len(w)):
            a=w.copy();b=w.copy();a[j]+=1e-6;b[j]-=1e-6
            finite=(m.linear_objective(a,z,ij,y,.02)[0]-m.linear_objective(b,z,ij,y,.02)[0])/2e-6
            self.assertAlmostEqual(finite,grad[j],places=7)

    def test_ranknet_gradient_with_dropout_mask(self):
        rng=np.random.default_rng(3);z=rng.normal(size=(6,3));theta=m.initialize(3,2,3);ij=m.pairs(6);y=rng.uniform(.1,.9,len(ij));mask=(rng.random((6,2))>.2)/.8
        _,grad=m.ranknet_objective(theta,z,ij,y,.002,mask)
        for part in range(3):
            for index in np.ndindex(theta[part].shape):
                a=[x.copy() for x in theta];b=[x.copy() for x in theta];a[part][index]+=1e-6;b[part][index]-=1e-6
                finite=(m.ranknet_objective(a,z,ij,y,.002,mask)[0]-m.ranknet_objective(b,z,ij,y,.002,mask)[0])/2e-6
                self.assertAlmostEqual(finite,grad[part][index],places=7)

    def test_group_split_prevents_shared_route_leakage(self):
        groups=np.repeat(np.arange(20),2);s=m.grouped_split(groups,42,SETTINGS['parameters']);self.assertEqual(len(set(np.concatenate(list(s.values())))),40)
        for a in s:
            for b in s:
                if a!=b:self.assertFalse(set(groups[s[a]])&set(groups[s[b]]))
        again=m.grouped_split(groups,42,SETTINGS['parameters'])
        for k in s:np.testing.assert_array_equal(s[k],again[k])

    def test_linear_recovers_soft_teacher_and_metrics(self):
        z=np.random.default_rng(8).normal(size=(30,3));truth=z@np.array([.3,-.4,.5]);ij=m.pairs(30);y=m.expit(truth[ij[:,0]]-truth[ij[:,1]])
        model=m.fit_linear(z,y,ij,1e-7);score=z@np.array(model['weights']);e=m.evaluate(score,truth,1,.1)
        self.assertLess(e['excess_log_loss'],1e-8);self.assertGreater(e['spearman_vs_teacher'],.999)
        tie=m.evaluate(np.zeros(30),truth,1,.1);self.assertIsNone(tie['spearman_vs_teacher']);self.assertGreater(tie['excess_log_loss'],e['excess_log_loss'])

    def test_ranknet_learns_and_reproduces(self):
        z=np.random.default_rng(4).normal(size=(24,3));truth=z@np.array([.3,-.4,.5]);ij=m.pairs(24);y=m.expit(truth[ij[:,0]]-truth[ij[:,1]])
        params=dict(SETTINGS['parameters'],ranknet_dropout=0.,ranknet_hidden=4)
        a=m.fit_ranknet(z,ij,y,params,42,fixed_epochs=120);b=m.fit_ranknet(z,ij,y,params,42,fixed_epochs=120)
        score=m.neural_score(z,[np.array(v) for v in a['theta']]);self.assertLess(m.pair_loss(score,ij,y),m.pair_loss(np.zeros(24),ij,y)-.02)
        for x,y in zip(a['theta'],b['theta']):np.testing.assert_array_equal(x,y)

    def test_teacher_weight_contract_and_safe_predictors(self):
        for features in [SETTINGS['input_features'],SETTINGS['alternate_input_features']]:
            self.assertFalse(set(features)&set(SETTINGS['excluded_predictors']))
            for w in [SETTINGS['teacher_weights'],*SETTINGS['teacher_sensitivity'].values()]:self.assertAlmostEqual(m.teacher_vector(features,w).sum(),1)

    @unittest.skipUnless((ROOT/'private_data/phase5/evaluation.json').exists(),'private experiment unavailable')
    def test_saved_artifacts_reconstruct_and_preserve_scope(self):
        data=json.loads((ROOT/'private_data/phase5/evaluation.json').read_text());self.assertEqual(data['feature_sha256'],m.sha(ROOT/'private_data/routes_features.csv'));self.assertEqual(data['config_sha256'],m.sha(ROOT/'outputs/project_config.json'));self.assertEqual(data['implementation_sha256'],m.sha(ROOT/'outputs/block4_ranker.py'))
        self.assertFalse(data['final_ranking_acceptance']);self.assertEqual(data['human_comparison_count'],0)
        with (ROOT/'private_data/routes_features.csv').open() as f:rows=list(csv.DictReader(f))
        lookup={r['route_id']:r for r in rows}
        for name,model in data['final_models'].items():
            x=np.array([[float(lookup[r][f]) for f in model['features']] for r in model['route_ids']]);z=(x-model['scaler_mean'])/model['scaler_scale']
            np.testing.assert_allclose(z@np.array(model['BT_linear']['weights']),model['scores']['BT_linear'],atol=1e-12)
            np.testing.assert_allclose(m.neural_score(z,[np.array(v) for v in model['RankNet']['theta']]),model['scores']['RankNet'],atol=1e-12)
        for exps in data['experiments'].values():
            for e in exps:
                split=e['split'];gs={k:{lookup[r]['evaluation_group'] for r in v['route_ids']} for k,v in split.items()}
                self.assertFalse(gs['train']&gs['test']);self.assertFalse(gs['validation']&gs['test']);self.assertFalse(gs['train']&gs['validation'])
                train=np.array([[float(lookup[r][f]) for f in data['final_models']['observed_segments_100' if 'observed_segment' in e['features'][2] else 'usable_profiles_96']['features']] for r in split['train']['route_ids']])
                np.testing.assert_allclose(train.mean(axis=0),e['scaler_mean'],atol=1e-10)
                self.assertLessEqual(e['RankNet']['selected_epoch'],e['RankNet']['epochs_run'])
        with (ROOT/'private_data/phase5/provisional_rankings.csv').open() as f:ranking=list(csv.DictReader(f))
        self.assertEqual(len(ranking),100);self.assertEqual(sum(not r['strict_BT_linear_rank'] for r in ranking),4)
        self.assertTrue(all(r['human_comparison_count']=='0' and r['complete_itinerary_verified']=='False' for r in ranking))

if __name__=='__main__':unittest.main()
