"""Phase Six: authenticated comparison core, transactional Elo, batch BT and sampling.

No public server is started here. Inject a server-validated session resolver into
make_app; its default rejects writes. CLI initializes an empty real store only.
"""
from __future__ import annotations
import argparse,csv,hashlib,hmac,io,json,math,os,secrets,sqlite3,time,uuid,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1] if Path(__file__).parent.name=='outputs' else Path(__file__).resolve().parent
if (ROOT/'work/phase4_runtime').exists():sys.path.insert(0,str(ROOT/'work/phase4_runtime'))
import numpy as np
from scipy.special import expit
from scipy.optimize import minimize
VERSION='6.0.0'
POLICY='coverage_posterior_disagreement_v1'
CONDITIONS={'dry_summer','snow','mixed','unknown'}

class Rejection(Exception):
    def __init__(self,message,status=400):super().__init__(message);self.status=status


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pseudonym(subject,key):
    if not isinstance(subject,str) or not subject or not isinstance(key,bytes) or len(key)<32:raise Rejection('Authenticated subject and private 32-byte HMAC key required',401)
    return hmac.new(key,subject.encode(),hashlib.sha256).hexdigest()


def check_voter(v):
    if not isinstance(v,str) or len(v)!=64 or any(x not in '0123456789abcdef' for x in v):raise Rejection('Invalid server voter pseudonym',401)


def components(ids,events):
    parent={r:r for r in ids}
    def find(x):
        while parent[x]!=x:parent[x]=parent[parent[x]];x=parent[x]
        return x
    for e in events:
        a,b=find(e['route_a']),find(e['route_b']);parent[max(a,b)]=min(a,b)
    groups={}
    for r in ids:groups.setdefault(find(r),[]).append(r)
    return list(groups.values())


def bt_fit(ids,events,l2):
    n=len(ids);lookup={r:i for i,r in enumerate(ids)};ij=np.array([[lookup[e['route_a']],lookup[e['route_b']]] for e in events],dtype=int).reshape(-1,2)
    y=np.array([1. if e['outcome']=='A' else 0. for e in events]);weight=np.ones(len(events))
    # Equal total contribution per voter limits prolific-voter domination.
    counts={v:sum(e['voter']==v for e in events) for v in {e['voter'] for e in events}}
    if len(events):weight=np.array([1/counts[e['voter']] for e in events])
    def objective(beta):
        d=beta[ij[:,0]]-beta[ij[:,1]] if len(ij) else np.array([])
        loss=np.sum(weight*(np.logaddexp(0,d)-y*d))+l2*np.dot(beta,beta)/2
        g=l2*beta.copy()
        if len(ij):
            err=weight*(expit(d)-y);np.add.at(g,ij[:,0],err);np.add.at(g,ij[:,1],-err)
        return float(loss),g
    fit=minimize(objective,np.zeros(n),jac=True,method='L-BFGS-B',options={'maxiter':1000,'gtol':1e-9})
    if not fit.success:raise RuntimeError('Batch BT optimizer failed: '+fit.message)
    beta=fit.x-fit.x.mean();precision=l2*np.eye(n)
    for (a,b),w in zip(ij,weight):
        p=expit(beta[a]-beta[b]);v=w*p*(1-p);precision[a,a]+=v;precision[b,b]+=v;precision[a,b]-=v;precision[b,a]-=v
    projection=np.eye(n)-np.ones((n,n))/n;cov=projection@np.linalg.inv(precision)@projection
    return beta,cov


def voter_bootstrap(ids,events,l2,repeats=100,seed=42):
    voters=sorted({e['voter'] for e in events})
    if len(voters)<2:return None
    rng=np.random.default_rng(seed);samples=[]
    for _ in range(repeats):
        chosen=rng.choice(voters,len(voters),replace=True);sample=[]
        for j,v in enumerate(chosen):sample += [dict(e,voter=f'resample_{j}') for e in events if e['voter']==v]
        beta,_=bt_fit(ids,sample,l2);samples.append(beta)
    low,high=np.quantile(samples,[.025,.975],axis=0)
    return {'method':'voter-resampled regularized BT','replicates':repeats,'lower':low.tolist(),'upper':high.tolist(),'scope':'Exploratory, prior/coverage dependent; not objective difficulty intervals.'}


class Store:
    def __init__(self,path,routes,manifest_hash,params,synthetic=None):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True);self.routes={r['route_id']:r for r in routes};self.ids=sorted(self.routes);self.params=params;self.manifest_hash=manifest_hash
        self.synthetic=synthetic or {r:[] for r in self.ids}
        self.connection=sqlite3.connect(self.path,timeout=10,isolation_level=None);self.connection.row_factory=sqlite3.Row
        self.connection.execute('PRAGMA journal_mode=WAL');self.connection.execute('PRAGMA foreign_keys=ON')
        self.connection.executescript('''
        CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS assignments(id TEXT PRIMARY KEY,voter TEXT NOT NULL,route_a TEXT NOT NULL,route_b TEXT NOT NULL,left_route TEXT NOT NULL,lane TEXT NOT NULL,policy TEXT NOT NULL,probability REAL NOT NULL,created REAL NOT NULL,expires REAL NOT NULL,manifest_hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT NOT NULL UNIQUE,assignment_id TEXT NOT NULL UNIQUE REFERENCES assignments(id),voter TEXT NOT NULL,route_a TEXT NOT NULL,route_b TEXT NOT NULL,left_route TEXT NOT NULL,outcome TEXT NOT NULL,completed_both INTEGER NOT NULL,conditions TEXT NOT NULL,lane TEXT NOT NULL,selection_probability REAL NOT NULL,received REAL NOT NULL,manifest_hash TEXT NOT NULL,payload_hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS elo(route_id TEXT PRIMARY KEY,rating REAL NOT NULL,votes INTEGER NOT NULL);
        CREATE TRIGGER IF NOT EXISTS immutable_event_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'append-only events');END;
        CREATE TRIGGER IF NOT EXISTS immutable_event_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'append-only events');END;
        CREATE TRIGGER IF NOT EXISTS immutable_assignment_update BEFORE UPDATE ON assignments BEGIN SELECT RAISE(ABORT,'immutable assignments');END;
        CREATE TRIGGER IF NOT EXISTS immutable_assignment_delete BEFORE DELETE ON assignments BEGIN SELECT RAISE(ABORT,'immutable assignments');END;
        ''')
        self.connection.execute('BEGIN IMMEDIATE')
        try:
            saved=self.connection.execute("SELECT value FROM metadata WHERE key='manifest'").fetchone()
            contract={'manifest':manifest_hash,'route_ids':self.ids,'params':params,'community_version':VERSION,'policy':POLICY,'synthetic_sha256':hashlib.sha256(json.dumps(self.synthetic,sort_keys=True).encode()).hexdigest()}
            contract_hash=hashlib.sha256(json.dumps(contract,sort_keys=True).encode()).hexdigest()
            if saved:
                old=self.connection.execute("SELECT value FROM metadata WHERE key='contract'").fetchone()[0]
                if saved[0]!=manifest_hash or old!=contract_hash:raise Rejection('Store roster/sampling contract changed; migrate explicitly',409)
            else:
                for k,v in [('manifest',manifest_hash),('contract',contract_hash),('route_ids',json.dumps(self.ids))]:self.connection.execute('INSERT INTO metadata VALUES (?,?)',(k,v))
                all_pairs=[(a,b) for i,a in enumerate(self.ids) for b in self.ids[i+1:]]
                rng=np.random.default_rng(params['sampling_seed']);selected=rng.permutation(len(all_pairs))[:round(len(all_pairs)*params['evaluation_pair_fraction'])]
                pool=[list(all_pairs[i]) for i in sorted(selected)];self.connection.execute('INSERT INTO metadata VALUES (?,?)',('evaluation_pool',json.dumps(pool)))
                for r in self.ids:self.connection.execute('INSERT INTO elo VALUES (?,?,0)',(r,params['elo_initial']))
            self.connection.commit()
        except Exception:self.connection.rollback();self.connection.close();raise
        self.eval_pool={tuple(p) for p in json.loads(self.connection.execute("SELECT value FROM metadata WHERE key='evaluation_pool'").fetchone()[0])}

    def close(self):self.connection.close()

    def events(self):return [dict(r) for r in self.connection.execute('SELECT * FROM events ORDER BY seq')]

    @staticmethod
    def qualified(e):return e['completed_both']==1 and e['conditions']=='dry_summer' and e['lane']=='training' and e['outcome']!='skip'

    def binary(self):return [e for e in self.events() if self.qualified(e) and e['outcome'] in ('A','B')]

    def _limits(self,voter,table,limit,now):
        field='created' if table=='assignments' else 'received'
        count=self.connection.execute(f'SELECT count(*) FROM {table} WHERE voter=? AND {field}>?',(voter,now-3600)).fetchone()[0]
        if count>=limit:raise Rejection('Hourly comparison limit reached',429)

    def distribution(self,voter,now):
        # Eligible pairs omit all previously answered and unexpired assigned pairs for this voter.
        seen={(e['route_a'],e['route_b']) for e in self.events() if e['voter']==voter}
        seen|={(r['route_a'],r['route_b']) for r in self.connection.execute('SELECT route_a,route_b FROM assignments WHERE voter=? AND expires>?',(voter,now))}
        eligible=[(a,b) for i,a in enumerate(self.ids) for b in self.ids[i+1:] if (a,b) not in seen]
        evaluation=[p for p in eligible if p in self.eval_pool];training=[p for p in eligible if p not in self.eval_pool]
        if not evaluation and not training:raise Rejection('No unseen comparison pairs remain',409)
        events=self.binary();groups=components(self.ids,events);component={r:i for i,g in enumerate(groups) for r in g};counts={r:0 for r in self.ids};pair_counts={p:0 for p in training}
        for e in self.events():
            if self.qualified(e):
                counts[e['route_a']]+=1;counts[e['route_b']]+=1
                p=(e['route_a'],e['route_b'])
                if p in pair_counts:pair_counts[p]+=1
        covariance=bt_fit(self.ids,events,self.params['bt_l2'])[1] if events else None
        index={r:i for i,r in enumerate(self.ids)}
        priority=[]
        for a,b in training:
            left,right=self.synthetic.get(a,[]),self.synthetic.get(b,[])
            disagreement=float(np.std(np.array(left)-np.array(right))) if left and right else 0
            bridge=float(component[a]!=component[b]);coverage=1/math.sqrt((1+counts[a])*(1+counts[b]))
            diversity=float(self.routes[a].get('evaluation_group')!=self.routes[b].get('evaluation_group'))
            ia,ib=index[a],index[b]
            uncertainty=math.sqrt(max(0,covariance[ia,ia]+covariance[ib,ib]-2*covariance[ia,ib]))/math.sqrt(2/self.params['bt_l2']) if covariance is not None else 0.
            priority.append((1+bridge+coverage+min(disagreement,2)+uncertainty+.25*diversity)/(1+pair_counts[(a,b)]))
        if training:
            weighted=np.array(priority);weighted/=weighted.sum();mix=self.params['training_uniform_mixture'];train_prob=mix/len(training)+(1-mix)*weighted
        else:train_prob=np.array([])
        lane_probability=self.params['evaluation_assignment_probability'] if evaluation and training else 1. if evaluation else 0.
        return evaluation,training,train_prob,lane_probability

    def assign(self,voter,now=None):
        check_voter(voter);now=time.time() if now is None else now;c=self.connection;c.execute('BEGIN IMMEDIATE')
        try:
            self._limits(voter,'assignments',self.params['assignment_limit_per_hour'],now)
            evaluation,training,prob,lane_p=self.distribution(voter,now)
            rng=np.random.default_rng(secrets.randbits(64));is_eval=bool(rng.random()<lane_p)
            if is_eval:pair=evaluation[int(rng.integers(len(evaluation)))];pair_p=1/len(evaluation);lane='evaluation';lane_mass=lane_p
            else:j=int(rng.choice(len(training),p=prob));pair=training[j];pair_p=float(prob[j]);lane='training';lane_mass=1-lane_p
            a,b=pair;left=a if rng.random()<.5 else b;identity=str(uuid.uuid4());joint=lane_mass*pair_p*.5
            c.execute('INSERT INTO assignments VALUES (?,?,?,?,?,?,?,?,?,?,?)',(identity,voter,a,b,left,lane,POLICY,joint,now,now+self.params['assignment_ttl_seconds'],self.manifest_hash));c.commit()
            return {'assignment_id':identity,'left':self.public_route(left),'right':self.public_route(b if left==a else a),'expires':now+self.params['assignment_ttl_seconds'],'conditions_prompt':'Compare dry-summer route difficulty if you have completed both routes.','response_options':['left','right','tie','skip'],'manifest_sha256':self.manifest_hash}
        except Exception:c.rollback();raise

    def public_route(self,r):return {k:self.routes[r].get(k,'') for k in ['route_id','canonical_name','source_url','yds_class']}

    def submit(self,voter,payload,now=None):
        check_voter(voter);now=time.time() if now is None else now
        keys={'event_id','assignment_id','choice','completed_both','conditions'}
        if not isinstance(payload,dict) or set(payload)!=keys:raise Rejection('Response must contain only event_id, assignment_id, choice, completed_both, conditions')
        for k in ['event_id','assignment_id']:
            try:
                if str(uuid.UUID(payload[k]))!=payload[k]:raise ValueError()
            except (ValueError,TypeError,AttributeError):raise Rejection('Canonical UUID required')
        if not isinstance(payload['choice'],str) or not isinstance(payload['conditions'],str) or payload['choice'] not in {'left','right','tie','skip'} or type(payload['completed_both']) is not bool or payload['conditions'] not in CONDITIONS:raise Rejection('Invalid comparison response')
        checksum=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest();c=self.connection;c.execute('BEGIN IMMEDIATE')
        try:
            old=c.execute('SELECT * FROM events WHERE id=?',(payload['event_id'],)).fetchone()
            if old:
                if old['voter']!=voter or old['payload_hash']!=checksum:raise Rejection('Event ID already used for different response',409)
                c.commit();return {'event_id':old['id'],'accepted':True,'idempotent_replay':True,'rating_updated':self.qualified(dict(old))}
            a=c.execute('SELECT * FROM assignments WHERE id=?',(payload['assignment_id'],)).fetchone()
            if a is None or a['voter']!=voter:raise Rejection('Assignment not owned by authenticated voter',403)
            if a['expires']<=now:raise Rejection('Assignment expired',409)
            if c.execute('SELECT 1 FROM events WHERE assignment_id=?',(a['id'],)).fetchone():raise Rejection('Assignment already answered',409)
            self._limits(voter,'events',self.params['vote_limit_per_hour'],now)
            choice=payload['choice'];outcome=choice if choice in {'tie','skip'} else ('A' if (a['left_route'] if choice=='left' else a['route_b'] if a['left_route']==a['route_a'] else a['route_a'])==a['route_a'] else 'B')
            c.execute('INSERT INTO events(id,assignment_id,voter,route_a,route_b,left_route,outcome,completed_both,conditions,lane,selection_probability,received,manifest_hash,payload_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (payload['event_id'],a['id'],voter,a['route_a'],a['route_b'],a['left_route'],outcome,int(payload['completed_both']),payload['conditions'],a['lane'],a['probability'],now,self.manifest_hash,checksum))
            e={'route_a':a['route_a'],'route_b':a['route_b'],'outcome':outcome,'completed_both':int(payload['completed_both']),'conditions':payload['conditions'],'lane':a['lane']}
            if self.qualified(e):
                ratings={r['route_id']:r['rating'] for r in c.execute('SELECT * FROM elo WHERE route_id IN (?,?)',(a['route_a'],a['route_b']))}
                expect=expit((ratings[a['route_a']]-ratings[a['route_b']])*math.log(10)/400);observed=1 if outcome=='A' else 0 if outcome=='B' else .5
                update=self.params['elo_k']*(observed-expect)
                c.execute('UPDATE elo SET rating=rating+?,votes=votes+1 WHERE route_id=?',(update,a['route_a']));c.execute('UPDATE elo SET rating=rating-?,votes=votes+1 WHERE route_id=?', (update,a['route_b']))
            c.commit();return {'event_id':payload['event_id'],'accepted':True,'idempotent_replay':False,'rating_updated':self.qualified(e)}
        except Exception:c.rollback();raise

    def replay(self):
        rating={r:float(self.params['elo_initial']) for r in self.ids};counts={r:0 for r in self.ids}
        for e in self.events():
            if not self.qualified(e):continue
            a,b=e['route_a'],e['route_b'];expected=expit((rating[a]-rating[b])*math.log(10)/400);y=1 if e['outcome']=='A' else 0 if e['outcome']=='B' else .5;change=self.params['elo_k']*(y-expected)
            rating[a]+=change;rating[b]-=change;counts[a]+=1;counts[b]+=1
        return rating,counts

    def summary(self,bootstrap=False):
        events=self.events();binary=self.binary();groups=components(self.ids,binary);beta,cov=bt_fit(self.ids,binary,self.params['bt_l2']);comp={r:i for i,g in enumerate(groups) for r in g};counts={r:0 for r in self.ids};voters={r:set() for r in self.ids}
        for e in binary:
            for r in [e['route_a'],e['route_b']]:counts[r]+=1;voters[r].add(e['voter'])
        elo={r['route_id']:dict(r) for r in self.connection.execute('SELECT * FROM elo')};replay,count=self.replay()
        if any(abs(elo[r]['rating']-replay[r])>1e-9 or elo[r]['votes']!=count[r] for r in self.ids):raise ValueError('Transactional Elo differs from event replay')
        connected=len(groups)==1;rank={self.ids[i]:j+1 for j,i in enumerate(np.argsort(-beta,kind='stable'))} if connected else {}
        ratings=[]
        for i,r in enumerate(self.ids):
            supported=counts[r]>=5 and len(voters[r])>=2;sd=math.sqrt(max(0,cov[i,i]));interval=[float(beta[i]-1.96*sd),float(beta[i]+1.96*sd)] if supported else None
            ratings.append({'route_id':r,'canonical_name':self.routes[r]['canonical_name'],'community_elo':elo[r]['rating'],'elo_comparison_count':elo[r]['votes'],
                'binary_comparison_count':counts[r],'distinct_binary_voters':len(voters[r]),'bt_beta':float(beta[i]) if counts[r] else None,
                'bt_laplace_interval':interval,'interval_scope':'Regularized curvature approximation, prior-dependent and ignores within-voter correlation.' if interval else None,
                'component_id':comp[r],'component_size':len(groups[comp[r]]),'global_rank':rank.get(r),'prior_only':count[r]==0})
        evaluation=[e for e in events if e['lane']=='evaluation'];eligible_eval=[e for e in evaluation if e['completed_both']==1 and e['conditions']=='dry_summer' and e['outcome'] in {'A','B'}]
        metric=None
        if eligible_eval:
            lookup={r:i for i,r in enumerate(self.ids)};d=np.array([beta[lookup[e['route_a']]]-beta[lookup[e['route_b']]] for e in eligible_eval]);y=np.array([e['outcome']=='A' for e in eligible_eval],dtype=float);p=expit(d)
            metric={'binary_count':len(d),'log_loss':float(np.mean(np.logaddexp(0,d)-y*d)),'brier':float(np.mean((p-y)**2)),
                    'scope':'Frozen pair holdout among known routes; descriptive monitoring, not untouched confirmatory evaluation or unseen-route validation.'}
        return {'community_version':VERSION,'manifest_sha256':self.manifest_hash,'route_count':len(self.ids),'event_count':len(events),'qualified_elo_events':sum(self.qualified(e) for e in events),
                'binary_training_events':len(binary),'evaluation_events':len(evaluation),'distinct_voters':len({e['voter'] for e in events}),'component_count':len(groups),'comparison_graph_connected':connected,
                'global_community_ranking_ready':connected and all(counts[r]>=5 and len(voters[r])>=2 for r in self.ids),
                'evaluation_pool_size':len(self.eval_pool),'evaluation_pool_sha256':hashlib.sha256(json.dumps(sorted(self.eval_pool)).encode()).hexdigest(),
                'ratings':ratings,'covariance':cov.tolist(),'voter_bootstrap':voter_bootstrap(self.ids,binary,self.params['bt_l2'],self.params['bootstrap_voter_replicates']) if bootstrap else None,
                'heldout_evaluation':metric,'human_labels_fabricated':False,'synthetic_prior_used_for_ratings':False}


def make_app(store_factory,authenticate=None,hmac_key=None):
    """WSGI boundary: authenticate(environ) must validate a server session/token.

    Body identities/route IDs are rejected. No client IP/User header is an identity.
    Default resolver denies writes. The factory returns a per-request connection.
    """
    authenticate=authenticate or (lambda environ:None)
    def app(environ,start_response):
        store=None
        try:
            method=environ.get('REQUEST_METHOD','GET');path=environ.get('PATH_INFO','')
            if method=='GET' and path=='/health':status=200;result={'service':'phase6-community','version':VERSION}
            elif method=='GET' and path=='/v1/ratings':
                store=store_factory();result=store.summary();result.pop('covariance');status=200
            elif method=='POST' and path in {'/v1/assignments','/v1/comparisons'}:
                subject=authenticate(environ)
                if not subject:raise Rejection('Authentication required',401)
                voter=pseudonym(subject,hmac_key)
                try:length=int(environ.get('CONTENT_LENGTH','0'))
                except ValueError:raise Rejection('Invalid body length')
                if length<0 or length>8192:raise Rejection('Body too large',413)
                try:payload=json.loads(environ['wsgi.input'].read(length)) if length else {}
                except (ValueError,UnicodeDecodeError):raise Rejection('Malformed JSON')
                store=store_factory()
                if path=='/v1/assignments':
                    if payload!={}:raise Rejection('Assignment identity is server-derived; body must be empty')
                    result=store.assign(voter);status=201
                else:result=store.submit(voter,payload);status=200
            else:raise Rejection('Endpoint not found',404)
        except Rejection as e:status=e.status;result={'error':str(e)}
        except Exception:status=500;result={'error':'Internal comparison service error'}
        finally:
            if store:store.close()
        body=json.dumps(result,allow_nan=False).encode();reason={200:'OK',201:'Created',400:'Bad Request',401:'Unauthorized',403:'Forbidden',404:'Not Found',409:'Conflict',413:'Payload Too Large',429:'Too Many Requests',500:'Internal Server Error'}[status]
        start_response(f'{status} {reason}',[('Content-Type','application/json'),('Content-Length',str(len(body))),('Cache-Control','no-store'),('X-Content-Type-Options','nosniff')]);return [body]
    return app


def run(root=ROOT):
    root=Path(root);out=root/'outputs' if (root/'outputs/project_config.json').exists() else root;config_path=out/'project_config.json';config=json.loads(config_path.read_text());params=config['phase6']['parameters']
    feature_path=root/'private_data/routes_features.csv'
    with feature_path.open() as f:routes=list(csv.DictReader(f))
    if len(routes)!=100 or len({r['route_id'] for r in routes})!=100:raise ValueError('Expected all 100 route IDs')
    prior_path=root/'private_data/phase5/evaluation.json';prior=json.loads(prior_path.read_text());model=prior['final_models']['observed_segments_100']
    if prior['feature_sha256']!=digest(feature_path):raise ValueError('Stale sampling model')
    # Model disagreement is a provisional acquisition signal, never initial human ratings.
    synthetic={r:[model['scores'][m][i] for m in ['teacher','BT_linear','RankNet']] for i,r in enumerate(model['route_ids'])}
    dest=root/'private_data/phase6';store=Store(root/config['phase6']['database'],routes,config['manifest_sha256'],params,synthetic)
    try:summary=store.summary(bootstrap=True)
    finally:store.close()
    summary.update(config_sha256=digest(config_path),implementation_sha256=digest(out/'block5_community.py'),feature_sha256=digest(feature_path),phase5_model_sha256=digest(prior_path))
    (dest/'community_snapshot.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    review={k:v for k,v in summary.items() if k not in {'ratings','covariance','voter_bootstrap'}};review.update(engineering_status='local_core_and_WSGI_contract_implemented',live_backend_deployed=False,github_status=config['phase6']['github_status'])
    (out/'phase6_review.json').write_text(json.dumps(review,indent=2,allow_nan=False)+'\n');write_report(config,summary,out/'phase6_report.md');print(json.dumps(review,indent=2));return summary


def write_report(config,summary,path):
    lines=['# Phase Six: comparison backend, community ratings and next steps',
      '\n**Local engineering is implemented. Live voting is not deployed.** The real community database contains '+str(summary['event_count'])+' events; no human votes were generated by the initialization workflow. Synthetic Phase Five scores remain separate.',
      '\n## Full phase map',
      '\n```mermaid\nflowchart LR\n  UI[Website comparison card] --> AUTH[Server-validated identity]\n  AUTH --> ASSIGN[Server assignment and randomized sides]\n  ASSIGN --> TRAIN[Training pair pool]\n  ASSIGN --> EVAL[Frozen random evaluation pool]\n  TRAIN --> EVENT[Append-only response transaction]\n  EVAL --> EVENT\n  EVENT --> FILTER{Qualified training response?}\n  FILTER --> ELO[Elo update; ties supported]\n  FILTER --> BT[Binary-only batch BT]\n  EVENT --> AUDIT[Replay and audit]\n  BT --> COVER[Coverage / components / uncertainty]\n  COVER --> SELECT[Coverage and disagreement sampling]\n  SELECT --> ASSIGN\n  EVAL --> METRIC[Separate held-out monitoring]\n```',
      '\n## Implemented plan',
      *['\n'+str(i+1)+'. '+step for i,step in enumerate(config['phase6']['execution_plan'])],
      '\n## Deliverables and current evidence',
      '\n- `outputs/block5_community.py`: SQLite store, Elo replay, batch BT/voter bootstrap, stochastic sampler and WSGI API factory.\n- `tests/test_block5.py`: fixture votes remain in temporary databases; they are not human observations.\n- `private_data/phase6/community.sqlite`: one real append-only event/assignment store; it does not copy the GPX/feature database.\n- `private_data/phase6/community_snapshot.json`: current honest ratings/coverage and provenance.\n- `outputs/phase6_review.json`: aggregate readiness and frozen evaluation-pool evidence.',
      f"\nCurrent roster: {summary['route_count']}; events: {summary['event_count']}; binary training responses: {summary['binary_training_events']}; connected components: {summary['component_count']}; reserved evaluation pairs: {summary['evaluation_pool_size']}.",
      '\nWith no votes, every route has neutral Elo 1500, zero vote counts, null BT estimates/intervals and no global community rank. Initial synthetic rankings are not presented as community evidence. The full graph initially has 100 isolated routes.',
      '\n## API and event contract',
      '\n| Endpoint | Behavior |\n|---|---|\n| GET /health | Service version |\n| GET /v1/ratings | Ratings, counts, component/prior flags; no voter identifiers or event payloads |\n| POST /v1/assignments | Authenticated server identity; empty request body; random left/right route card |\n| POST /v1/comparisons | Authenticated assignment owner; idempotent response recording and atomic rating update |',
      '\nResponse body:',
      '\n```json\n{"event_id":"canonical UUID","assignment_id":"server UUID","choice":"left|right|tie|skip","completed_both":true,"conditions":"dry_summer|snow|mixed|unknown"}\n```',
      '\nPersisted events include server-normalized A/B/tie/skip outcome, canonical route IDs, roster hash, pseudonymous voter, assigned display side, lane/policy, exact selection probability, received timestamp, experience/conditions and payload hash. Unknown body fields, user-supplied identities/route IDs, expired/foreign assignments and duplicate answers are rejected. Equal event-ID retries return the original acceptance without another Elo update; conflicting retries return 409.',
      '\nSQLite BEGIN IMMEDIATE makes event insert and both Elo changes one transaction. SQL triggers prevent event/assignment update or deletion. The server enforces per-pseudonym hourly limits and an 8 KiB request limit. Auth must be injected from a real server session verifier; the default rejects writes. HMAC pseudonymization requires a private 32-byte-or-longer key and does not retain plaintext account IDs. This is a tested API boundary, not a complete production identity provider or abuse-prevention service.',
      '\n## Rating semantics and uncertainty',
      '\nLarger community rating means harder. Elo starts at 1500 with K=24. Only training-lane, self-reported completed-both, dry-summer non-skip events update Elo; qualified ties use 0.5. Batch BT excludes ties and fits only qualified binary events, with sum-zero scores and L2=1. Each voter has equal total contribution in a batch. Snow/mixed/unknown-condition or inexperienced responses are recorded separately and do not silently affect the dry-summer ranking.',
      '\nElo replay is verified against stored ratings/counts. Batch BT reports connected components; component offsets are prior-driven when disconnected. Global ranks are withheld until connectivity, and readiness additionally requires at least five binary comparisons and two distinct voters per route. These counts are engineering pilot gates, not statistical guarantees.',
      '\nRegularized curvature intervals are withheld for low-evidence routes and labeled prior-dependent; they ignore within-voter dependence. Voter-resampled BT intervals are available only with at least two voters, with 100 bootstrap resamples by default. They remain exploratory and sensitive to coverage, voter sampling and regularization. No intervals or rankings are fabricated for the empty store.',
      '\n## Pair selection and evaluation isolation',
      '\nA deterministic roster-frozen random 20% of all 4,950 pairs (990) is reserved for evaluation. That set is persisted with a checksum and cannot enter training Elo/BT or active acquisition. Twenty percent of assignments choose the evaluation lane when both pools have eligible pairs; its pair draw is uniform. Training selections mix 20% uniform probability with 80% weighted acquisition combining component bridges, low-vote coverage, regularized BT score-difference variance, Phase Five model disagreement, group diversity and repeat-count penalties.',
      '\nSynthetic model disagreement is an initial heuristic acquisition signal, not measured epistemic uncertainty; it never initializes community ratings. The regularized score-difference variance is an approximate prior-sensitive uncertainty signal, not a validated posterior. A 0.5 expected outcome alone is not treated as uncertainty. Previously answered or outstanding pairs are excluded for that voter. Left/right order is uniformly random. Events retain the marginal lane × pair × side probability conditional on the current eligible history; exhausted-lane probabilities are renormalized.',
      '\nThe held-out lane evaluates comparisons among known routes, not generalization to unseen routes. Monitoring its metrics during development consumes confirmatory independence; freeze a model/checkpoint and time-separated evaluation stream before final claims. No propensity-corrected community accuracy is claimed in this local phase.',
      '\n## GitHub connection',
      '\nAuthenticated Chrome GitHub access is verified on October 1, 2026. All 26 canonical source/config/roster/audit/documentation/test files were committed through the browser. CLI API transport remains unavailable; local Git remote configuration is blocked by read-only .git permissions.',
      '\nThe user selected the existing public [ElliottGorsuch/14ers repository](https://github.com/ElliottGorsuch/14ers) for canonical code and documentation only, and Base44 hosting. Private tracks, cookies, derived per-route features/models and community records remain local.',
      '\n## Base44 integration boundary',
      '\nBase44 native backend functions use Deno and its request-derived client/session API. The current Python WSGI/SQLite core is a tested reference implementation, not a directly deployable Base44 function. Next-phase integration must port these contracts and atomic/idempotent semantics into supported Base44 backend storage, or connect a separately hosted Python service. Datastore transaction/concurrency behavior must be verified before live votes. [Official Base44 client/backend guide](https://docs.base44.com/sdk-getting-started/client).',
      '\n## Next steps to finish live Phase Six and proceed to Phase Seven',
      '\n1. GitHub code/docs publication is complete; preserve private-data exclusions and verify Base44 GitHub synchronization.\n2. Implement the selected Base44 backend adapter or hosted Python bridge and attach a real authenticated session resolver, a private HMAC secret, HTTPS and deployment-level rate/concurrency controls.\n3. Wire comparison cards to the assignment/response endpoints, including both-routes experience, conditions, tie/skip, accessible side order and retry handling.\n4. Pilot with real completed-both dry-summer comparisons; inspect duplicates, coverage, component bridges, condition exclusions and voter concentration.\n5. Schedule BT snapshots and audit replay; preserve the random evaluation lane and add a frozen time-separated evaluation checkpoint.\n6. Proceed to the recorded Phase Seven graphs/clusters/hover/location/neighbor integration. Full-itinerary review and independent human evidence remain needed for final route-difficulty acceptance.',
      '\n## Reproduction',
      '\n```bash\npython3 outputs/block5_community.py\npython3 tests/test_block5.py\n```',
      '\nThe CLI initializes/audits the real store and writes reports; it never opens a public port or fabricates votes. The WSGI factory is exercised in-process by tests, so no local-server network permission is needed.',
      '\nReferences: [Bradley–Terry identifying constraints](https://arxiv.org/abs/2205.04341), [BT uncertainty study](https://academic.oup.com/imaiai/article/12/2/1073/7017369), [OWASP REST security](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html).']
    Path(path).write_text('\n'.join(lines)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--project-root',type=Path,default=ROOT);run(p.parse_args().project_root)
