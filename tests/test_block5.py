"""Phase Six fixtures: never written to the real community database."""
import importlib.util,io,json,sqlite3,tempfile,unittest,uuid
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('community',ROOT/'outputs/block5_community.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
np=m.np
PARAMS=json.loads((ROOT/'outputs/project_config.json').read_text())['phase6']['parameters']

class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'fixture.sqlite';self.params=dict(PARAMS,assignment_limit_per_hour=1000,vote_limit_per_hour=1000,bootstrap_voter_replicates=8)
        self.routes=[{'route_id':f'r{i}','canonical_name':f'Fixture {i}','evaluation_group':str(i%2),'source_url':'https://example.test','yds_class':'2'} for i in range(8)]
        self.store=m.Store(self.path,self.routes,'fixture-manifest',self.params);self.voter=m.pseudonym('fixture-user',b'x'*32)
    def tearDown(self):self.store.close();self.temp.cleanup()
    def payload(self,a,choice='left',completed=True,conditions='dry_summer'):
        return {'event_id':str(uuid.uuid4()),'assignment_id':a['assignment_id'],'choice':choice,'completed_both':completed,'conditions':conditions}
    def assignment(self,lane='training',voter=None,now=100):
        voter=voter or self.voter
        with patch.object(m.secrets,'randbits',return_value=3 if lane=='evaluation' else 0):
            a=self.store.assign(voter,now)
        r=self.store.connection.execute('SELECT * FROM assignments WHERE id=?',(a['assignment_id'],)).fetchone()
        self.assertEqual(r['lane'],lane)
        return a,dict(r)

    def test_frozen_evaluation_pool_and_exact_probability(self):
        pool=self.store.eval_pool.copy();self.assertEqual(len(pool),round(28*.2))
        evaluation,training,prob,lane=self.store.distribution(self.voter,100);self.assertFalse(set(training)&pool);self.assertEqual(set(evaluation),pool);self.assertAlmostEqual(float(prob.sum()),1);self.assertEqual(lane,.2)
        a=self.store.assign(self.voter,100);row=self.store.connection.execute('SELECT * FROM assignments WHERE id=?',(a['assignment_id'],)).fetchone();p=(row['route_a'],row['route_b'])
        expected=lane/len(evaluation)*.5 if row['lane']=='evaluation' else (1-lane)*prob[training.index(p)]*.5;self.assertAlmostEqual(row['probability'],expected)
        other=m.Store(self.path,self.routes,'fixture-manifest',self.params);self.assertEqual(other.eval_pool,pool);other.close()
        with self.assertRaises(m.Rejection):m.Store(self.path,self.routes,'changed-manifest',self.params)

    def test_idempotency_rating_direction_and_canonical_side(self):
        a,row=self.assignment();left=a['left']['route_id'];right=a['right']['route_id'];p=self.payload(a)
        result=self.store.submit(self.voter,p,101);self.assertTrue(result['rating_updated']);first=self.store.summary();ratings={r['route_id']:r['community_elo'] for r in first['ratings']}
        self.assertEqual(ratings[left],1512);self.assertEqual(ratings[right],1488);self.assertAlmostEqual(sum(ratings.values()),8*1500)
        retry=self.store.submit(self.voter,p,9999);self.assertTrue(retry['idempotent_replay']);self.assertEqual(self.store.summary()['event_count'],1)
        with self.assertRaises(m.Rejection):self.store.submit(self.voter,dict(p,choice='right'),102)
        with self.assertRaises(m.Rejection):self.store.submit(self.voter,dict(p,event_id=str(uuid.uuid4())),102)
        stored=self.store.events()[0];self.assertEqual(stored['outcome'],'A' if left==row['route_a'] else 'B')

    def test_foreign_expired_assignment_and_invalid_body(self):
        a,_=self.assignment();p=self.payload(a)
        with self.assertRaises(m.Rejection):self.store.submit(m.pseudonym('other',b'x'*32),p,101)
        with self.assertRaises(m.Rejection):self.store.submit(self.voter,p,2000)
        with self.assertRaises(m.Rejection):self.store.submit(self.voter,dict(p,route_a='r0'),101)
        with self.assertRaises(m.Rejection):self.store.submit(self.voter,dict(p,completed_both=1),101)
        with self.assertRaises(m.Rejection):self.store.submit(self.voter,dict(p,choice=[]),101)
        self.assertEqual(len(self.store.events()),0)

    def test_evaluation_skip_conditions_and_experience_do_not_train(self):
        cases=[('evaluation','left',True,'dry_summer'),('training','skip',True,'dry_summer'),('training','left',False,'dry_summer'),('training','left',True,'snow')]
        for i,(lane,choice,done,conditions) in enumerate(cases):
            voter=m.pseudonym(str(i),b'x'*32);a,_=self.assignment(lane,voter);r=self.store.submit(voter,self.payload(a,choice,done,conditions),101);self.assertFalse(r['rating_updated'])
        self.assertEqual(len(self.store.events()),4);self.assertFalse(self.store.binary());s=self.store.summary();self.assertEqual(s['qualified_elo_events'],0);self.assertEqual(s['evaluation_events'],1);self.assertTrue(all(r['community_elo']==1500 for r in s['ratings']))

    def test_tie_updates_elo_but_not_binary_bt(self):
        a,_=self.assignment();self.store.submit(self.voter,self.payload(a,'tie'),101);s=self.store.summary();self.assertEqual(s['qualified_elo_events'],1);self.assertEqual(s['binary_training_events'],0);self.assertEqual(sum(r['elo_comparison_count'] for r in s['ratings']),2)
        self.assertTrue(all(r['community_elo']==1500 for r in s['ratings']))

    def test_append_only_and_atomic_rollback(self):
        a,_=self.assignment();self.store.submit(self.voter,self.payload(a),101)
        with self.assertRaises(sqlite3.IntegrityError):self.store.connection.execute('DELETE FROM events')
        with self.assertRaises(sqlite3.IntegrityError):self.store.connection.execute("UPDATE events SET outcome='B'")
        b,_=self.assignment(voter=m.pseudonym('new',b'x'*32));p=self.payload(b)
        self.store.connection.execute("CREATE TRIGGER fail_rating BEFORE UPDATE ON elo BEGIN SELECT RAISE(ABORT,'fixture rollback');END")
        with self.assertRaises(sqlite3.IntegrityError):self.store.submit(m.pseudonym('new',b'x'*32),p,101)
        self.assertEqual(len(self.store.events()),1)
        self.assertFalse(self.store.connection.execute('SELECT 1 FROM events WHERE id=?',(p['event_id'],)).fetchone())
        self.store.connection.execute('DROP TRIGGER fail_rating');self.store.summary()

    def test_limits_unseen_pairs_and_probability_renormalization(self):
        a,_=self.assignment();self.store.submit(self.voter,self.payload(a),101);ev,tr,_,_=self.store.distribution(self.voter,102);pair=tuple(sorted([a['left']['route_id'],a['right']['route_id']]));self.assertNotIn(pair,ev+tr)
        self.store.params['assignment_limit_per_hour']=0
        with self.assertRaises(m.Rejection) as ctx:self.store.assign(self.voter,103)
        self.assertEqual(ctx.exception.status,429)

    def test_bt_center_connectivity_and_voter_bootstrap(self):
        ids=['a','b','c'];events=[]
        for v in ['one','two','three']:
            events += [dict(route_a='a',route_b='b',outcome='A',voter=v),dict(route_a='b',route_b='c',outcome='A',voter=v)]
        beta,cov=m.bt_fit(ids,events,1);self.assertAlmostEqual(beta.sum(),0,places=12);self.assertGreater(beta[0],beta[1]);self.assertGreater(beta[1],beta[2]);self.assertTrue(np.isfinite(cov).all());self.assertEqual(len(m.components(ids,events)),1)
        boot=m.voter_bootstrap(ids,events,1,repeats=8);self.assertEqual(boot['replicates'],8);self.assertTrue(np.isfinite(boot['lower']).all());self.assertIsNone(m.voter_bootstrap(ids,[events[0]],1,8))
        self.assertEqual(len(m.components(ids,[])),3)

    def test_wsgi_auth_ownership_retries_and_malformed_requests(self):
        def factory():return m.Store(self.path,self.routes,'fixture-manifest',self.params)
        def request(app,path,payload,authenticated=False):
            body=json.dumps(payload).encode();status=[];environ={'REQUEST_METHOD':'POST','PATH_INFO':path,'CONTENT_LENGTH':str(len(body)),'wsgi.input':io.BytesIO(body),'fixture_auth':authenticated}
            answer=b''.join(app(environ,lambda s,h:status.append(s)));return int(status[0].split()[0]),json.loads(answer)
        denied=m.make_app(factory);self.assertEqual(request(denied,'/v1/assignments',{})[0],401)
        app=m.make_app(factory,authenticate=lambda e:'fixture-user' if e.get('fixture_auth') else None,hmac_key=b'x'*32)
        code,a=request(app,'/v1/assignments',{},True);self.assertEqual(code,201);p=self.payload(a);code,r=request(app,'/v1/comparisons',p,True);self.assertEqual(code,200);self.assertTrue(r['accepted'])
        code,r=request(app,'/v1/comparisons',p,True);self.assertEqual(code,200);self.assertTrue(r['idempotent_replay'])
        self.assertEqual(request(app,'/v1/assignments',{'voter':'spoofed'},True)[0],400)

    @unittest.skipUnless((ROOT/'private_data/phase6/community_snapshot.json').exists(),'real empty store not initialized')
    def test_real_snapshot_is_honest_and_versioned(self):
        s=json.loads((ROOT/'private_data/phase6/community_snapshot.json').read_text());self.assertEqual(s['route_count'],100);self.assertEqual(s['evaluation_pool_size'],990);self.assertFalse(s['human_labels_fabricated']);self.assertFalse(s['synthetic_prior_used_for_ratings'])
        self.assertEqual(s['config_sha256'],m.digest(ROOT/'outputs/project_config.json'));self.assertEqual(s['implementation_sha256'],m.digest(ROOT/'outputs/block5_community.py'))
        if not s['event_count']:
            self.assertEqual(s['component_count'],100);self.assertFalse(s['global_community_ranking_ready']);self.assertTrue(all(r['global_rank'] is None and r['bt_beta'] is None and r['community_elo']==1500 for r in s['ratings']))

if __name__=='__main__':unittest.main()
