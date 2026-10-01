"""Phase Five: grouped synthetic-label evaluation and provisional route ranking.

NumPy RankNet is a genuine shared neural scorer, with a separately tested pairwise
analytic gradient. Synthetic labels describe the chosen teacher, never human truth.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import importlib.metadata
import json
import os
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1] if Path(__file__).parent.name=='outputs' else Path(__file__).resolve().parent
if (ROOT/'work/phase4_runtime').exists():sys.path.insert(0,str(ROOT/'work/phase4_runtime'))
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'work/matplotlib_cache'))
import numpy as np
from scipy.optimize import minimize
from scipy.special import expit
from scipy.stats import spearmanr,kendalltau
from sklearn.model_selection import GroupShuffleSplit
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits
VERSION='5.0.0'


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def pairs(n):return np.column_stack(np.triu_indices(n,1))


def teacher_vector(features,weights):
    w=np.zeros(len(features))
    for j,f in enumerate(features):
        key=('distance' if f.endswith('distance_mi') else 'gain' if f.endswith('gain_ft') else
             'medium_density' if f.endswith('crux_density_medium') else
             'extreme_density' if f.endswith('crux_density_extreme') else
             'class' if f=='yds_encoded' else 'longest_medium' if f.endswith('longest_medium_mi') else
             'longest_extreme' if f.endswith('longest_extreme_mi') else 'risk_mean')
        w[j]=weights[key]/4 if key=='risk_mean' else weights[key]
    if not np.isclose(w.sum(),1):raise ValueError('Teacher weights must sum to one')
    return w


def pair_loss(scores,ij,target):
    delta=scores[ij[:,0]]-scores[ij[:,1]]
    return float(np.mean(np.logaddexp(0,delta)-target*delta))


def linear_objective(w,z,ij,y,l2):
    dx=z[ij[:,0]]-z[ij[:,1]];d=dx@w
    return float(np.mean(np.logaddexp(0,d)-y*d)+l2*np.sum(w*w)/2),dx.T@(expit(d)-y)/len(y)+l2*w


def fit_linear(z,y,ij,l2):
    fit=minimize(linear_objective,np.zeros(z.shape[1]),args=(z,ij,y,l2),jac=True,method='L-BFGS-B',options={'maxiter':1000,'gtol':1e-9})
    if not fit.success:raise RuntimeError('BT optimization failed: '+fit.message)
    return {'weights':fit.x.tolist(),'optimizer_iterations':int(fit.nit),'objective':float(fit.fun)}


def initialize(p,h,seed):
    rng=np.random.default_rng(seed)
    return [rng.normal(0,1/np.sqrt(p),(p,h)),np.zeros(h),rng.normal(0,1/np.sqrt(h),h)]


def neural_score(z,theta):return np.tanh(z@theta[0]+theta[1])@theta[2]


def ranknet_objective(theta,z,ij,y,l2,mask=None):
    w,b,v=theta;hidden=np.tanh(z@w+b);mask=np.ones_like(hidden) if mask is None else mask
    out=hidden*mask;scores=out@v;delta=scores[ij[:,0]]-scores[ij[:,1]]
    err=(expit(delta)-y)/len(y);ds=np.zeros(len(z))
    np.add.at(ds,ij[:,0],err);np.add.at(ds,ij[:,1],-err)
    dh=ds[:,None]*v[None,:]*mask*(1-hidden*hidden)
    grad=[z.T@dh+l2*w,dh.sum(axis=0),out.T@ds+l2*v]
    loss=pair_loss(scores,ij,y)+l2*(np.sum(w*w)+np.sum(v*v))/2
    return float(loss),grad


def fit_ranknet(z,ij,y,params,seed,validation=None,fixed_epochs=None):
    theta=initialize(z.shape[1],params['ranknet_hidden'],seed);mom=[np.zeros_like(a) for a in theta];vel=[a.copy() for a in mom]
    rng=np.random.default_rng(seed+1000);best=[a.copy() for a in theta];best_loss=float('inf');best_epoch=0;history=[]
    limit=fixed_epochs or params['ranknet_max_epochs'];drop=params['ranknet_dropout']
    for epoch in range(1,limit+1):
        mask=(rng.random((len(z),params['ranknet_hidden']))>=drop)/(1-drop)
        loss,grad=ranknet_objective(theta,z,ij,y,params['ranknet_l2'],mask)
        for j,g in enumerate(grad):
            mom[j]=.9*mom[j]+.1*g;vel[j]=.999*vel[j]+.001*g*g
            theta[j]-=params['ranknet_learning_rate']*(mom[j]/(1-.9**epoch))/(np.sqrt(vel[j]/(1-.999**epoch))+1e-8)
        val=pair_loss(neural_score(validation[0],theta),validation[1],validation[2]) if validation else pair_loss(neural_score(z,theta),ij,y)
        history.append({'epoch':epoch,'train_loss':float(loss),'validation_soft_loss':val})
        if val<best_loss-1e-6:best_loss=val;best=[a.copy() for a in theta];best_epoch=epoch
        if validation and epoch-best_epoch>=params['ranknet_patience']:break
    chosen=best if validation else theta
    if not all(np.isfinite(a).all() for a in chosen):raise ValueError('Nonfinite RankNet parameters')
    return {'theta':[a.tolist() for a in chosen],'epochs_run':epoch,'selected_epoch':best_epoch if validation else epoch,'history':history}


def grouped_split(groups,seed,params):
    index=np.arange(len(groups));trainval,test=next(GroupShuffleSplit(n_splits=1,test_size=params['test_group_fraction'],random_state=seed).split(index,groups=groups))
    train,val=next(GroupShuffleSplit(n_splits=1,test_size=params['validation_group_fraction_of_remaining'],random_state=seed+100).split(trainval,groups=np.array(groups)[trainval]))
    result={'train':trainval[train],'validation':trainval[val],'test':test}
    gs=[set(np.array(groups)[a]) for a in result.values()]
    if any(gs[i]&gs[j] for i in range(3) for j in range(i)):raise ValueError('Shared evaluation group leakage')
    if min(map(len,result.values()))<3:raise ValueError('Insufficient held-out routes')
    return result


def evaluate(scores,reference,temperature,margin,ij=None):
    ij=pairs(len(scores)) if ij is None else ij;truth=expit((reference[ij[:,0]]-reference[ij[:,1]])/temperature);pred=expit(scores[ij[:,0]]-scores[ij[:,1]])
    entropy=-np.mean(truth*np.log(np.clip(truth,1e-12,1))+(1-truth)*np.log(np.clip(1-truth,1e-12,1)))
    loss=pair_loss(scores,ij,truth);active=np.abs(truth-.5)>=margin
    return {'route_count':len(scores),'pair_count':len(ij),'soft_log_loss':loss,'teacher_entropy':float(entropy),'excess_log_loss':float(loss-entropy),
            'probability_mse_vs_teacher':float(np.mean((pred-truth)**2)),
            'non_tie_pair_count':int(active.sum()),'non_tie_pair_accuracy':float(np.mean(np.where(pred[active]==.5,.5,((pred[active]>.5)==(truth[active]>.5)).astype(float)))) if active.any() else None,
            'spearman_vs_teacher':float(spearmanr(scores,reference).statistic) if np.std(scores)>0 else None,
            'kendall_vs_teacher':float(kendalltau(scores,reference).statistic) if np.std(scores)>0 else None}


def bootstrap_groups(scores,reference,groups,params,seed):
    rng=np.random.default_rng(seed);unique=np.unique(groups);values=[]
    for _ in range(params['bootstrap_group_replicates']):
        chosen=rng.choice(unique,len(unique),replace=True);idx=np.concatenate([np.flatnonzero(np.array(groups)==g) for g in chosen])
        if len(idx)<3 or np.std(reference[idx])==0:continue
        ij=pairs(len(idx));ij=ij[idx[ij[:,0]]!=idx[ij[:,1]]]
        values.append(evaluate(scores[idx],reference[idx],params['teacher_temperature'],params['non_tie_probability_margin'],ij)['excess_log_loss'])
    return {'metric':'excess_log_loss','unit':'held-out route groups','replicates':len(values),'percentile_95':np.quantile(values,[.025,.975]).tolist()}


def experiment(rows,features,teacher_features,settings,seed):
    params=settings['parameters'];groups=[r['evaluation_group'] for r in rows];split=grouped_split(groups,seed,params)
    x=np.array([[float(r[f]) for f in teacher_features] for r in rows]);scaler=StandardScaler().fit(x[split['train']]);zall=scaler.transform(x)
    weights=teacher_vector(teacher_features,settings['teacher_weights']);reference=zall@weights/params['teacher_temperature']
    cols=[teacher_features.index(f) for f in features];z=zall[:,cols];tr,va,te=(split[k] for k in ['train','validation','test'])
    ij=pairs(len(tr));y=expit(reference[tr][ij[:,0]]-reference[tr][ij[:,1]]);vip=pairs(len(va));vy=expit(reference[va][vip[:,0]]-reference[va][vip[:,1]])
    linear=fit_linear(z[tr],y,ij,params['bt_l2']);net=fit_ranknet(z[tr],ij,y,params,seed,(z[va],vip,vy))
    score={'BT_linear':z[te]@np.array(linear['weights']),'RankNet':neural_score(z[te],[np.array(v) for v in net['theta']]),'constant_tie':np.zeros(len(te))}
    return {'seed':seed,'features':features,'scaler_mean':scaler.mean_.tolist(),'scaler_scale':scaler.scale_.tolist(),
            'split':{k:{'route_ids':[rows[i]['route_id'] for i in idx],'group_count':len(set(np.array(groups)[idx])),
                       'class_counts':{str(c):sum(int(rows[i]['yds_class'])==c for i in idx) for c in range(1,6)}} for k,idx in split.items()},
            'train_pair_count':len(ij),'validation_pair_count':len(vip),'BT_linear':linear,'RankNet':net,
            'metrics':{k:evaluate(v,reference[te],1,params['non_tie_probability_margin']) for k,v in score.items()},
            'group_bootstrap':{k:bootstrap_groups(v,reference[te],np.array(groups)[te],params,seed+500) for k,v in score.items() if k!='constant_tie'},
            'test_scores':{k:v.tolist() for k,v in score.items()},'test_teacher_scores':reference[te].tolist()}


def rank(scores):
    # Deterministic stable ordinal positions; exact ties retain input roster order.
    order=np.argsort(-np.asarray(scores),kind='stable');result=np.empty(len(order),dtype=int);result[order]=np.arange(1,len(order)+1);return result


def final_model(rows,features,settings,epochs):
    params=settings['parameters'];x=np.array([[float(r[f]) for f in features] for r in rows]);scaler=StandardScaler().fit(x);z=scaler.transform(x)
    reference=z@teacher_vector(features,settings['teacher_weights'])/params['teacher_temperature'];ij=pairs(len(rows));y=expit(reference[ij[:,0]]-reference[ij[:,1]])
    linear=fit_linear(z,y,ij,params['bt_l2']);net=fit_ranknet(z,ij,y,params,42,fixed_epochs=epochs)
    scores={'teacher':reference,'BT_linear':z@np.array(linear['weights']),'RankNet':neural_score(z,[np.array(v) for v in net['theta']])}
    alternatives={'main':reference}
    for name,w in settings['teacher_sensitivity'].items():alternatives[name]=z@teacher_vector(features,w)/params['teacher_temperature']
    ranks=np.array([rank(v) for v in alternatives.values()])
    return {'features':features,'route_ids':[r['route_id'] for r in rows],'scaler_mean':scaler.mean_.tolist(),'scaler_scale':scaler.scale_.tolist(),
            'BT_linear':linear,'RankNet':net,'scores':{k:v.tolist() for k,v in scores.items()},
            'ranks':{k:rank(v).tolist() for k,v in scores.items()},'teacher_weight_sensitivity':{'scenario_ranks':{k:rank(v).tolist() for k,v in alternatives.items()},
            'rank_min':ranks.min(axis=0).tolist(),'rank_max':ranks.max(axis=0).tolist(),'scope':'Scenario range, not a statistical confidence interval.'}}


def write_outputs(data,rows,out,dest):
    dest.mkdir(parents=True,exist_ok=True);(dest/'evaluation.json').write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
    main=data['final_models']['observed_segments_100'];strict=data['final_models']['usable_profiles_96'];lookup={r:i for i,r in enumerate(strict['route_ids'])}
    export=[]
    for i,r in enumerate(rows):
        d={k:r[k] for k in ['route_id','canonical_name','yds_class','source_url','evaluation_group','qa_flags','profile_valid_distance_fraction']}
        d.update(model_version=VERSION,score_scope='synthetic_teacher_accepted_recorded_segments',human_comparison_count=0,complete_itinerary_verified=False)
        for model in ['teacher','BT_linear','RankNet']:
            d['qualified_'+model+'_score']=main['scores'][model][i];d['qualified_'+model+'_rank']=main['ranks'][model][i]
            j=lookup.get(r['route_id']);d['strict_'+model+'_rank']=strict['ranks'][model][j] if j is not None else ''
        d['weight_scenario_rank_min']=main['teacher_weight_sensitivity']['rank_min'][i];d['weight_scenario_rank_max']=main['teacher_weight_sensitivity']['rank_max'][i];export.append(d)
    with (dest/'provisional_rankings.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(export[0]));w.writeheader();w.writerows(export)
    write_report(data,export,out/'phase5_report.md');write_preview(data,export,dest/'phase5_overview.png')


def write_report(data,rows,path):
    lines=['# Phase Five: provisional ranking baselines and model card',
      '\n**Engineering complete; objective route difficulty remains unvalidated.** These models learn an explicit synthetic teacher from real recorded-track features. All source scope/QA flags remain unchanged; human comparison count is zero.',
      '\n## Plan and delivered files',
      '\nThe six-step plan freezes provenance, records website requirements, defines a weighted teacher, fits linear Bradley–Terry and neural RankNet scorers, evaluates route-group holdouts/ablations, and delivers rankings, sensitivity plots and this model card.',
      '\n- `private_data/phase5/provisional_rankings.csv`: all 100 route IDs, qualified scores/ranks, strict 96-route ranks, QA and weight-scenario ranges.\n- `private_data/phase5/evaluation.json`: splits, teacher/student parameters, scalers, selected epochs, training history, scores, metrics, group-bootstrap intervals and provenance.\n- `private_data/phase5/phase5_overview.png`: held-out synthetic metrics and ranking sensitivity.\n- `outputs/block4_ranker.py` and `tests/test_block4.py`: reproducible implementation and numerical/leakage checks.',
      '\n## Synthetic teacher and models',
      '\nLarger score means harder under this chosen heuristic. Population-standardize features using training routes only for each holdout. Teacher weights: class 0.35, extreme density 0.125, medium density 0.075, mean four risk encodings 0.15, recorded distance 0.10, gain 0.10, longest medium 0.05 and longest extreme 0.05. These are project assumptions, not measured causal contributions. Pair targets are sigmoid(teacher A − teacher B).',
      '\nLinear Bradley–Terry optimizes pairwise soft cross-entropy with L2=0.02. The neural RankNet uses one shared 8-unit tanh scorer, Adam, dropout=0.1, L2=0.002 and validation early stopping. It is implemented in NumPy with analytic gradients to avoid adding a heavyweight framework; finite-difference tests verify backpropagation. Both models operate on feature differences through a score, not on route IDs, clusters, Elo or teacher scores as predictor columns.',
      '\nThe linear model has the same form as the synthetic teacher. Good imitation is expected and is a pipeline sanity check, not independent scientific validation. Near-tie accuracy excludes teacher probabilities within 0.1 of 0.5; exact student ties receive half credit. MSE compares probabilities to the teacher, not to observed human outcomes. No empirical human calibration, NDCG or objective safety metric is claimed.',
      '\n## Grouped holdout evaluation',
      '\nSplit groups before generating pairs: 20% test groups, then 20% of remaining groups for validation. Shared-path connected groups cannot cross partitions. Seeds 42/43/44 repeat the experiment, with nine/eleven inputs and strict 96/qualified 100 cohorts. The teacher is fixed to eleven features for each comparison, so nine-feature students lack the longest-section inputs. Validation chooses RankNet stopping; test routes never fit scalers, optimizers or stopping criteria.',
      '\n| Cohort / inputs | Model | Mean test soft loss | Mean excess over teacher entropy | Mean non-tie accuracy | Mean Spearman vs teacher |\n|---|---|---:|---:|---:|---:|']
    for key,exp in data['experiments'].items():
        for model in ['BT_linear','RankNet','constant_tie']:
            ms=[e['metrics'][model] for e in exp];avg=lambda k:np.mean([m[k] for m in ms if m[k] is not None]) if any(m[k] is not None for m in ms) else float('nan')
            correlation=f"{avg('spearman_vs_teacher'):.3f}" if np.isfinite(avg('spearman_vs_teacher')) else '—'
            lines.append(f"| {key} | {model} | {avg('soft_log_loss'):.4f} | {avg('excess_log_loss'):.4f} | {100*avg('non_tie_pair_accuracy'):.1f}% | {correlation} |")
    lines+=['\nThe regularized linear scorer is the default baseline: it has lower mean held-out soft loss than RankNet in these experiments and is easier to inspect. RankNet remains a tested comparison model; no advantage over the linear teacher is claimed. Future independent human labels may justify a different model.',
      '\nConstant-tie scores have undefined rank correlation; null is retained rather than claiming zero correlation. Repeated splits overlap and are not independent folds. Bootstrap intervals resample held-out route groups (200 replicates per split), not individual pairs; they describe synthetic-test sensitivity and depend on the provisional overlap grouping.',
      '\n| Experiment | Seed | Train / validation / test routes | Train / validation / test groups | Held-out pairs | RankNet selected epoch |\n|---|---:|---|---|---:|---:|']
    for key,exps in data['experiments'].items():
        for e in exps:
            counts=' / '.join(str(len(e['split'][k]['route_ids'])) for k in ['train','validation','test']);groups=' / '.join(str(e['split'][k]['group_count']) for k in ['train','validation','test'])
            lines.append(f"| {key} | {e['seed']} | {counts} | {groups} | {e['metrics']['BT_linear']['pair_count']} | {e['RankNet']['selected_epoch']} |")
    lines+=['\nExact route IDs, held-out class counts and intervals are in evaluation JSON. Even 4,950 possible pairs among 100 routes are only 100 route observations; pair counts are not an independent sample size.',
      '\n## Provisional full-roster outputs and sensitivity',
      '\nFinal display models refit on their entire descriptive cohort using median validation-selected epochs from the corresponding eleven-feature experiments. Their in-sample rankings are separate from held-out evaluation. Four routes lack strict densities and therefore have blank strict ranks; accepted-segment observations support the explicitly qualified 100-route view. Neither view has verified full dry itineraries.',
      '\nWeight scenarios include the original nine-feature heuristic, a technical emphasis and an endurance emphasis. Rank ranges across these scenarios are assumption sensitivity, not uncertainty confidence intervals. RankNet/linear disagreement is likewise not a measured safety uncertainty. Scores from differently fitted cohorts cannot be directly compared.',
      '\nIllustrative highest synthetic teacher positions in the qualified view (not a recommended objective difficulty ordering):',
      '\n| Position | Route | Class | Weight-scenario position range |\n|---:|---|---:|---|']
    for r in sorted(rows,key=lambda r:r['qualified_teacher_rank'])[:12]:lines.append(f"| {r['qualified_teacher_rank']} | {r['canonical_name']} | {r['yds_class']} | {r['weight_scenario_rank_min']}–{r['weight_scenario_rank_max']} |")
    lines+=['\n## Model card and next-phase readiness',
      '\nIntended use: local exploratory synthetic baselines, implementation validation, and planning community comparison collection. Not validated for route recommendations, conditions, legal access or a real-world difficulty ranking. Missing itinerary scope, smoothing sensitivity, ordinal encoding assumptions, correlated variables and shared geometry remain limitations. No human votes were fabricated.',
      '\nPhase Six comparison-schema/collection engineering can begin. Obtain independent route-pair evidence, preserve random evaluation comparisons outside active selection, check graph connectivity, and evaluate human outcomes before claiming calibrated ranking quality. Complete-itinerary coverage and the two metadata cases remain required for final acceptance.',
      '\n## Website requirement recorded',
      '\nThe final website should retain PCA/UMAP/t-SNE graphs, named exploratory clusters with feature summaries/stability, route hover cards, geographic location/source links, clicked-route similar neighbors and alternate-route comparisons. Geographic location is distinct from embedding position. Cluster definitions must be based on standardized input features and validated for stability, not manually inferred from UMAP islands. This phase records the requirement; it does not deploy a website or assert discovered clusters.',
      '\n## Reproduction',
      '\n```bash\npython3 outputs/block4_ranker.py\npython3 tests/test_block4.py\n```',
      '\nModel/data/config hashes and installed runtime versions are in evaluation JSON. Saved NumPy arrays in JSON support score reconstruction without executable pickle files.',
      '\nPrimary method references: [RankNet paper](https://www.microsoft.com/en-us/research/publication/learning-to-rank-using-gradient-descent/), [GroupShuffleSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GroupShuffleSplit.html), [SciPy L-BFGS-B](https://docs.scipy.org/doc/scipy/reference/optimize.minimize-lbfgsb.html).']
    Path(path).write_text('\n'.join(lines)+'\n')


def write_preview(data,rows,path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(1,3,figsize=(15,5),layout='constrained');fig.patch.set_facecolor('#f6f5ef')
    names=['BT_linear','RankNet','constant_tie'];exps=data['experiments']['usable_profiles_96_11']
    means=[np.mean([e['metrics'][m]['excess_log_loss'] for e in exps]) for m in names]
    ax[0].bar(['Linear BT','RankNet','Always tie'],means,color=['#4c897d','#d9aa54','#b18074']);ax[0].set_title('Held-out imitation error · 96 routes');ax[0].set_ylabel('Soft loss above teacher entropy (lower better)')
    for i,v in enumerate(means):ax[0].text(i,v,f'{v:.4f}',ha='center',va='bottom')
    ax[1].scatter([r['qualified_teacher_rank'] for r in rows],[r['qualified_RankNet_rank'] for r in rows],c=[int(r['yds_class']) for r in rows],cmap='viridis',vmin=1,vmax=5,s=25);ax[1].plot([1,100],[1,100],color='#888',ls='--');ax[1].set_xlabel('Synthetic teacher rank');ax[1].set_ylabel('RankNet rank');ax[1].set_title('Qualified 100-route display fit')
    selected=[r for r in rows if r['route_id'] in data['highlight_route_ids']];names=[r['canonical_name'].replace(' Peak','').replace(' - ','\n') for r in selected]
    for i,r in enumerate(selected):ax[2].plot([r['weight_scenario_rank_min'],r['weight_scenario_rank_max']],[i,i],color='#bd9450',lw=4);ax[2].scatter(r['qualified_teacher_rank'],i,color='#366f62',s=35,zorder=3)
    ax[2].set_yticks(range(len(selected)),names,fontsize=8);ax[2].set_xlim(0,102);ax[2].set_xlabel('Synthetic position (1 = highest score)');ax[2].set_title('Weight-scenario ranges · not confidence intervals')
    for a in ax:a.spines[['top','right']].set_visible(False);a.grid(alpha=.15)
    fig.suptitle('Phase Five · provisional synthetic ranking baselines\nNo human validation · recorded segments only',fontsize=15);fig.savefig(path,dpi=150,facecolor=fig.get_facecolor());plt.close(fig)


def run(root=ROOT):
    root=Path(root);out=root/'outputs' if (root/'outputs/project_config.json').exists() else root
    config_path=out/'project_config.json';config=json.loads(config_path.read_text());settings=config['phase5'];feature=root/'private_data/routes_features.csv';review=out/'phase3_review.json'
    snapshot=json.loads(review.read_text())
    if snapshot['feature_table_sha256']!=sha(feature) or snapshot['config_sha256']!=sha(config_path):raise ValueError('Stale feature/config provenance')
    with feature.open(newline='') as f:rows=list(csv.DictReader(f))
    if len(rows)!=100 or len({r['route_id'] for r in rows})!=100:raise ValueError('Expected 100 unique routes')
    cohorts={'usable_profiles_96':([r for r in rows if all(r[f] for f in settings['input_features'])],settings['input_features']),
             'observed_segments_100':(rows,settings['alternate_input_features'])}
    data={'model_version':VERSION,'scope':'provisional_synthetic_teacher_imitation','feature_sha256':sha(feature),'config_sha256':sha(config_path),
          'implementation_sha256':sha(out/'block4_ranker.py'),'phase3_review_sha256':sha(review),'manifest_sha256':config['manifest_sha256'],
          'parameters':settings['parameters'],'teacher_weights':settings['teacher_weights'],'teacher_sensitivity':settings['teacher_sensitivity'],
          'runtime':{p:importlib.metadata.version(p) for p in ['numpy','scipy','scikit-learn','matplotlib']},
          'human_comparison_count':0,'final_ranking_acceptance':False,'highlight_route_ids':config['phase4']['highlight_route_ids'],
          'website_requirements':config['website_requirements'],'experiments':{},'final_models':{}}
    with threadpool_limits(limits=1):
        for name,(subset,features) in cohorts.items():
            for size in [11,9]:
                selected=features if size==11 else [f for f in features if 'longest_' not in f]
                key=name+'_'+str(size);data['experiments'][key]=[]
                for seed in settings['parameters']['split_seeds']:
                    print('Training',key,seed,flush=True);data['experiments'][key].append(experiment(subset,selected,features,settings,seed))
            epochs=int(np.median([e['RankNet']['selected_epoch'] for e in data['experiments'][name+'_11']]))
            data['final_models'][name]=final_model(subset,features,settings,epochs)
    write_outputs(data,rows,out,root/'private_data/phase5');return data


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--project-root',type=Path,default=ROOT);run(p.parse_args().project_root)
