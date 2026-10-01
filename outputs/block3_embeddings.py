"""Phase Four: local PCA, UMAP and t-SNE exploration with explicit data scope."""
from __future__ import annotations
import argparse
import csv
import hashlib
import importlib.metadata
import json
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] if Path(__file__).parent.name == 'outputs' else Path(__file__).resolve().parent
# Isolated, ignored package target; never alter the user's Python installation.
if (ROOT/'work/phase4_runtime').exists():
    sys.path.insert(0, str(ROOT/'work/phase4_runtime'))
os.environ.setdefault('NUMBA_CACHE_DIR', str(ROOT/'work/numba_cache'))
os.environ.setdefault('NUMBA_NUM_THREADS', '1')
os.environ.setdefault('MPLCONFIGDIR', str(ROOT/'work/matplotlib_cache'))
import numpy as np
import scipy
from scipy.optimize import linear_sum_assignment
from sklearn import __version__ as sklearn_version
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE, trustworthiness
from sklearn.metrics import pairwise_distances
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits
import umap
from plotly.offline import get_plotlyjs

VERSION = '4.1.0'
LABELS = {'source_track_distance_mi':'Recorded distance', 'source_track_gain_ft':'Recorded gain',
          'source_track_crux_density_medium':'Medium crux density', 'source_track_crux_density_extreme':'Extreme crux density',
          'yds_encoded':'Class encoding', 'exposure_encoded':'Exposure', 'rockfall_encoded':'Rockfall',
          'route_finding_encoded':'Route finding', 'commitment_encoded':'Commitment',
          'source_track_longest_medium_mi':'Longest medium section (mi)',
          'source_track_longest_extreme_mi':'Longest extreme section (mi)',
          'observed_segment_crux_density_medium':'Accepted-segment medium density (%)',
          'observed_segment_crux_density_extreme':'Accepted-segment extreme density (%)'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def neighbors(x, k):
    d = pairwise_distances(x)
    np.fill_diagonal(d, np.inf)
    return np.argsort(d, axis=1, kind='stable')[:, :k]


def neighbor_agreement(a, b, k):
    na, nb = neighbors(a,k), neighbors(b,k)
    return float(np.mean([len(set(x)&set(y))/k for x,y in zip(na,nb)]))


def metrics(x, embedding, k):
    return {'trustworthiness':float(trustworthiness(x,embedding,n_neighbors=k)),
            'mean_neighbor_overlap':neighbor_agreement(x,embedding,k)}


def fit_pca(x):
    scaler = StandardScaler()
    z = scaler.fit_transform(x)
    pca = PCA(svd_solver='full', whiten=False)
    scores = pca.fit_transform(z)
    # Orient each component by its largest absolute coefficient; sign has no meaning.
    for j in range(len(pca.components_)):
        if pca.components_[j,np.argmax(np.abs(pca.components_[j]))] < 0:
            pca.components_[j] *= -1
            scores[:,j] *= -1
    pop_sd = np.sqrt(pca.explained_variance_*(len(z)-1)/len(z))
    loading = pca.components_.T * pop_sd
    return scaler, pca, z, scores, loading, pop_sd


def bootstrap_loadings(x, reference, repeats, seed):
    rng = np.random.default_rng(seed)
    values=[]
    for _ in range(repeats):
        sample=x[rng.integers(0,len(x),len(x))]
        _,p,_,_,load,_=fit_pca(sample)
        a,b=linear_sum_assignment(-np.abs(reference[:2]@p.components_[:2].T))
        ordered=np.empty((x.shape[1],2))
        for target,component in zip(a,b):
            sign=1 if np.dot(reference[target],p.components_[component])>=0 else -1
            ordered[:,target]=load[:,component]*sign
        values.append(ordered)
    low,high=np.quantile(values,[.025,.975],axis=0)
    return low,high


def fit_nonlinear(z, method, params, seed, variant=None):
    if method=='UMAP':
        n,md=variant or (params['umap_n_neighbors'],params['umap_min_dist'])
        fit=umap.UMAP(n_neighbors=min(n,len(z)-1),min_dist=md,n_components=2,
                      metric='euclidean',random_state=seed,n_jobs=1,init='spectral')
        coords=fit.fit_transform(z)
        return coords,{'n_neighbors':min(n,len(z)-1),'min_dist':md,'seed':seed}
    perplexity=variant or params['tsne_perplexity']
    fit=TSNE(n_components=2,perplexity=min(perplexity,len(z)-1),random_state=seed,
             learning_rate='auto',init='random' if seed==params['sensitivity_seed'] else 'pca',max_iter=params['tsne_max_iter'],metric='euclidean')
    coords=fit.fit_transform(z)
    return coords,{'perplexity':min(perplexity,len(z)-1),'seed':seed,'init':'random' if seed==params['sensitivity_seed'] else 'pca','kl_divergence':float(fit.kl_divergence_)}


def analyze_cohort(rows,features,params):
    x=np.array([[float(r[f]) for f in features] for r in rows])
    if not np.isfinite(x).all() or len(x)<=2*params['neighbor_metric_k']:
        raise ValueError('Cohort must have finite features and enough rows for neighbor metrics')
    scaler,pca,z,scores,loading,sd=fit_pca(x)
    low,high=bootstrap_loadings(x,pca.components_,params['pca_bootstrap_replicates'],params['random_seed'])
    biplot=scores[:,:2]/sd[:2]
    result={'count':len(rows),'features':features,'class_counts':{str(i):sum(int(r['yds_class'])==i for r in rows) for i in range(1,6)},
            'feature_mean':scaler.mean_.tolist(),'feature_scale':scaler.scale_.tolist(),
            'constant_features':[features[i] for i,s in enumerate(scaler.var_) if s==0],
            'explained_variance_ratio':pca.explained_variance_ratio_.tolist(),
            'components':pca.components_.tolist(), 'correlation_loadings':loading[:,:2].tolist(),
            'loading_bootstrap_low':low.tolist(),'loading_bootstrap_high':high.tolist(),
            'pca_scores':scores[:,:2].tolist(), 'pca_biplot_scores':biplot.tolist(),
            'standardized_features':z.tolist(),
            'PCA':{'coords':biplot.tolist(),**metrics(z,biplot,params['neighbor_metric_k']),
                   'metrics_on':'component-SD-normalized correlation biplot scores'},
            'rows':[{k:r[k] for k in ('route_id','canonical_name','yds_class','profile_qa_pass','qa_flags','evaluation_group','profile_valid_distance_fraction')}
                    | {'values':{f:float(r[f]) for f in features}} for r in rows]}
    for method in ['UMAP','t-SNE']:
        coords,details=fit_nonlinear(z,method,params,params['random_seed'])
        variants=([tuple(v) for v in params['umap_variants']] if method=='UMAP' else params['tsne_perplexity_variants'])
        sensitivity=[]
        for variant in [None]+variants:
            seed=params['sensitivity_seed'] if variant is None else params['random_seed']
            alt,setting=fit_nonlinear(z,method,params,seed,variant)
            sensitivity.append({**setting,**metrics(z,alt,params['neighbor_metric_k']),
                                'neighbor_agreement_with_default':neighbor_agreement(coords,alt,params['neighbor_metric_k'])})
        result[method]={'coords':coords.tolist(),**details,**metrics(z,coords,params['neighbor_metric_k']),
                        'sensitivity':sensitivity}
    # Controlled encoding comparison: change only YDS buckets from nonlinear to 1..5.
    linear=x.copy();linear[:,features.index('yds_encoded')]=[int(r['yds_class']) for r in rows]
    _,alternate,zalt,alternate_scores,_,_=fit_pca(linear)
    result['linear_class_sensitivity']={'pc1_pc2_variance_pct':float(alternate.explained_variance_ratio_[:2].sum()*100),
        'standardized_neighbor_agreement':neighbor_agreement(z,zalt,params['neighbor_metric_k'])}
    legacy=[i for i,f in enumerate(features) if 'longest_' not in f]
    if len(legacy)<len(features):
        _,old,zold,_,_,_=fit_pca(x[:,legacy])
        result['longest_section_ablation']={'legacy_two_pc_variance_pct':float(old.explained_variance_ratio_[:2].sum()*100),
            'input_neighbor_agreement':neighbor_agreement(z,zold,params['neighbor_metric_k'])}
    result['feature_correlations']=np.corrcoef(z.T).tolist()
    return result


def write_report(analysis,path):
    cohorts=analysis['cohorts'];a=cohorts['usable_profiles_96'];q=cohorts['numeric_qa_37'];ratings=cohorts['ratings_only_100']
    p=lambda v:f'{100*v:.1f}%'
    lines=['# Phase Four: PCA, UMAP and t-SNE exploration',
      '\nThe three methods are built and run locally on real Phase Three features. This is **recorded-track exploration**, not a complete-itinerary difficulty ranking. No data is published or sent to an external analysis service.',
      '\n## What to open',
      '\nOpen `private_data/phase4/route_exploration.html` in Codex for all three plots. Select the cohort and color, hover for route/feature details, and click a route to see its five nearest neighbors in the standardized input space. PCA offers true correlation loading arrows and a scree plot. The page is self-contained, including Plotly; it works offline.',
      '\n`private_data/phase4/phase4_overview.png` is the static comparison. `private_data/phase4/analysis.json` saves coordinates, scaler mean/scale, PCA components/loadings, bootstrap intervals, input features, parameters, diagnostics and provenance. Together these support reproducible exploration without additional pickle artifacts.',
      '\n## Cohorts and selection bias',
      '\n| View | Routes | Inputs | Interpretation |\n|---|---:|---|---|',
      '| Numeric QA subset | 37 | Eleven profile/class/risk features | Recorded profiles passing the current numeric checks; dry full-itinerary scope still unverified |',
      '| All usable profiles | 96 | Same eleven features | Exploratory comparison that includes sensitivity/gap flags; four missing-density rows excluded |',
      '| Accepted-segment comparison | 100 | Eleven features using accepted-segment densities | Includes four sub-95% profiles; observational scope and excluded-length bounds explicit |',
      '| Ratings only | 100 | Class plus four risk encodings | Full-roster comparison independent of GPX coverage; no endurance or steepness inputs |',
      '\nThe numeric-QA subset contains **no Class 5 routes**, so it underrepresents the most technical end of the cohort. The usable-profile view has '+str(a['class_counts']['5'])+' Class 5 routes. Results that differ between these views can reflect selection bias as well as quality. Each view gets its own fitted scaler and embeddings; axes cannot be compared numerically across views. No profile is imputed.',
      '\n## PCA findings',
      '\n| Cohort | PC1 | PC2 | First two combined |\n|---|---:|---:|---:|']
    for key,c in cohorts.items():
        v=c['explained_variance_ratio'];lines.append(f'| {key} | {p(v[0])} | {p(v[1])} | {p(sum(v[:2]))} |')
    lines+=['\nPCA was fitted after population standardization, without whitening. Components are oriented by their largest coefficient for reproducible presentation; a sign flip changes neither fit nor meaning. The correlation biplot divides scores by each component\'s population SD and draws feature-score correlations on the same axes. Neighbor metrics use those displayed coordinates.',
      '\nFor the broader 96-track cohort, feature-score correlations are:',
      '\n| Feature | PC1 | PC2 | PC1 bootstrap 95% range | PC2 bootstrap 95% range |\n|---|---:|---:|---|---|']
    for i,f in enumerate(a['features']):
        l=a['correlation_loadings'][i];lo=a['loading_bootstrap_low'][i];hi=a['loading_bootstrap_high'][i]
        lines.append(f'| {LABELS[f]} | {l[0]:+.3f} | {l[1]:+.3f} | {lo[0]:+.2f} to {hi[0]:+.2f} | {lo[1]:+.2f} to {hi[1]:+.2f} |')
    for axis in [0,1]:
        order=sorted(range(len(a['features'])),key=lambda i:abs(a['correlation_loadings'][i][axis]),reverse=True)[:3]
        names=', '.join(f"{LABELS[a['features'][i]]} ({a['correlation_loadings'][i][axis]:+.2f})" for i in order)
        lines.append(f'\nPC{axis+1} is most strongly associated with {names}. These are interpretations of the observed loadings, not predefined endurance/technical axes.')
    lines+=['\nThe 200 bootstrap fits refit the scaler and PCA, then align component identity/signs. Their percentile ranges describe sensitivity to resampling this small cohort. They assume exchangeable routes and do not correct shared-path dependence; broad ranges should reduce confidence in naming an axis. These are exploratory stability intervals, not population-confidence claims.',
      '\n## UMAP and t-SNE findings',
      '\nUMAP defaults: 15 neighbors, minimum distance 0.1, Euclidean metric, seed 42. The sensitivity set uses 5/30 neighbors, minimum distance 0.5, and seed 43. t-SNE defaults: perplexity 10, PCA initialization, automatic learning rate, 1,500 iterations, seed 42; comparisons use perplexities 5/20/30 and an alternative random initialization with seed 43 (changing the seed alone with deterministic PCA initialization is not a meaningful initialization stress test).',
      '\nFor each view, trustworthiness measures unexpected neighbors introduced by the 2D map (closer to 1 is better). Five-neighbor overlap measures how many exact high-dimensional neighbors remain in the plot (closer to 1 is better). Distances tied by identical ratings can make exact-neighbor scores sensitive to tie ordering. No metric validates a real difficulty ordering.',
      '\n| View | Method | Trustworthiness (k=5) | Mean input-neighbor overlap | Alternate seed/init neighbor agreement |\n|---|---|---:|---:|---:|']
    for key,c in cohorts.items():
        for method in ['PCA','UMAP','t-SNE']:
            fit=c[method];seed='—' if method=='PCA' else p(fit['sensitivity'][0]['neighbor_agreement_with_default'])
            lines.append(f"| {key} | {method} | {fit['trustworthiness']:.3f} | {p(fit['mean_neighbor_overlap'])} | {seed} |")
    lines+=['\nFor the broader 96-track cohort, nonlinear sensitivity results are:',
      '\n| Method | Variation | Trustworthiness | Agreement with default map neighbors |\n|---|---|---:|---:|']
    for method in ['UMAP','t-SNE']:
        for v in a[method]['sensitivity']:
            label=f"neighbors {v['n_neighbors']}, min_dist {v['min_dist']}, seed {v['seed']}" if method=='UMAP' else f"perplexity {v['perplexity']}, seed {v['seed']}, init {v['init']}"
            lines.append(f"| {method} | {label} | {v['trustworthiness']:.3f} | {p(v['neighbor_agreement_with_default'])} |")
    lines+=['\nUMAP and t-SNE preserve local relationships, and neither provides PCA-style feature loading arrows. Apparent islands, their spacing, orientation and area are not calibrated difficulty differences or evidence of natural route clusters. Parameter/seed agreement shows which local neighborhoods are more stable. t-SNE is a visualization here; this implementation does not offer an out-of-sample transform.',
      '\n## Encoding and feature choices',
      '\nThe eleven-feature model uses recorded distance, smoothed positive gain, medium/extreme crux density, nonlinear Class 1–5 encoding (1/2/4/8/16), and four ordinal source risk labels (0–4). Density remains percent-grade based: medium 20–35%, extreme above 35%. Longest continuous medium and extreme sections are included at user request. Total steep mileage remains outside the main matrix. Standardization gives every feature equal initial variance; correlated steepness measures can therefore receive extra weight. The nine-feature ablation quantifies that choice.',
      f"\nReplacing nonlinear class encoding with linear Class 1–5 changes the broader cohort's first-two-PC variance to {a['linear_class_sensitivity']['pc1_pc2_variance_pct']:.1f}% and retains {p(a['linear_class_sensitivity']['standardized_neighbor_agreement'])} of input-space five-neighbor relationships. The selected encoding is a modeling assumption, not measured spacing between climbing grades.",
      '\n## Readiness and next decisions',
      '\n**Phase Four exploratory engineering is complete:** all three methods, parameter/seed checks, PCA bootstrap intervals, local interactive plots and a written comparison are delivered. **Final complete-itinerary PCA/ranking acceptance remains pending:** 0 of 100 routes have verified full dry-itinerary features. Shared approaches and incomplete returns still affect recorded distances and profiles.',
      '\nBefore Phase Five, resolve itinerary scope and the two outstanding metadata cases, review profile sensitivity/gaps, and inspect shared-path evaluation groups. A synthetic ranking baseline can be engineered separately, but these exploratory plots do not establish objective route difficulty or predict safety. Fit scaler/embeddings on training data only for supervised evaluation; the cohort-wide fits here are descriptive.',
      '\n## Reproduction and sources',
      '\n```bash\npython outputs/block3_embeddings.py\npython tests/test_block3.py\n```',
      '\nThe module uses the ignored local `work/phase4_runtime` package target when present. Else install the recorded versions into your chosen research environment. Official PyPI wheel downloads and hashes are retained under `work/phase4_wheels`; runtime versions and source/config/code/feature hashes are stored in `analysis.json`. Nothing relies on a remote plotting CDN.',
      '\nMethods: [scikit-learn PCA](https://scikit-learn.org/stable/modules/generated/sklearn.decomposition.PCA.html), [StandardScaler](https://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.StandardScaler.html), [trustworthiness](https://scikit-learn.org/stable/modules/generated/sklearn.manifold.trustworthiness.html), [UMAP parameters](https://umap-learn.readthedocs.io/en/latest/parameters.html), [UMAP reproducibility](https://umap-learn.readthedocs.io/en/latest/reproducibility.html), [t-SNE parameters and cautions](https://scikit-learn.org/stable/modules/generated/sklearn.manifold.TSNE.html).']
    extra=['\n## Four qualified profiles: observations and uncertainty',
           '\nAll four GPX files exist. The unchanged 100 m edge filter excludes sparse jumps; these profiles fall below the unchanged 95% recorded-length gate. Strict source-track densities remain missing. The additional 100-route map uses densities on accepted segments for every route, without imputation or bridging excluded edges. This does not promote any numeric-QA or complete-itinerary flags.',
           '\nThe following lower/upper ranges allocate excluded recorded chord distance outside or entirely inside each individual grade band. Upper bounds are separate band-wise possibilities, not simultaneous allocations. They cannot bound true terrain distance, unrecorded approaches/descents or smoothing error.',
           '\n| Route | Accepted recorded distance | Observed medium density | Medium chord bound | Observed extreme density | Extreme chord bound |\n|---|---:|---:|---|---:|---|']
    for r in analysis['coverage_cases']:
        band=lambda b:f"{float(r['recorded_chord_crux_density_'+b+'_lower_pct']):.1f}–{float(r['recorded_chord_crux_density_'+b+'_upper_pct']):.1f}%"
        extra.append(f"| {r['canonical_name']} | {100*float(r['profile_valid_distance_fraction']):.1f}% | {float(r['observed_segment_crux_density_medium']):.1f}% | {band('medium')} | {float(r['observed_segment_crux_density_extreme']):.1f}% | {band('extreme')} |")
    extra+=['\nResearch retained the current route identities. Older Columbia lines need matching against its rerouted trail; opposite-direction traverse reports and mixed Snowmass S-Ridge/West Slope tracks cannot substitute automatically. Candidate evidence and disposition are recorded in the existing project config.']
    for src in analysis['four_profile_research']['sources']:
        extra.append(f"- [{src['route_id']} source]({src['url']}): {src['finding']}")
    extra+=['\n## Requested route comparisons',
            '\nThese are actual recorded profiles, not complete round-trip totals. The common 96-profile model uses all eleven variables for neighbor comparisons.',
            '\n| Route | Class | Recorded distance (mi) | Recorded gain (ft) | Longest medium (mi) | Longest extreme (mi) |\n|---|---:|---:|---:|---:|---:|']
    for r in a['rows']:
        if r['route_id'] in analysis['highlight_route_ids']:
            v=r['values'];extra.append(f"| {r['canonical_name']} | {r['yds_class']} | {v['source_track_distance_mi']:.2f} | {v['source_track_gain_ft']:.0f} | {v['source_track_longest_medium_mi']:.3f} | {v['source_track_longest_extreme_mi']:.3f} |")
    extra.append('\nClosest standardized-input neighbors for the requested routes:')
    near=neighbors(np.array(a['standardized_features']),5)
    for i,r in enumerate(a['rows']):
        if r['route_id'] in analysis['highlight_route_ids']:
            extra.append('- '+r['canonical_name']+': '+', '.join(a['rows'][j]['canonical_name'] for j in near[i])+'.')
    ab=a['longest_section_ablation']
    extra.append(f"\nAdding longest sections retains {100*ab['input_neighbor_agreement']:.1f}% of the original nine-feature input-neighbor relationships. The original nine-feature first-two-PC variance was {ab['legacy_two_pc_variance_pct']:.1f}%. This ablation exposes correlated-feature weighting; an increase or decrease in variance captured alone does not establish a better model.")
    extra.append('\nCorrelations involving the added features:')
    corr=np.array(a['feature_correlations'])
    for f in ('source_track_longest_medium_mi','source_track_longest_extreme_mi'):
        i=a['features'].index(f);order=sorted((j for j in range(len(a['features'])) if j!=i),key=lambda j:abs(corr[i,j]),reverse=True)[:3]
        extra.append('- '+LABELS[f]+': '+', '.join(LABELS[a['features'][j]]+f" ({corr[i,j]:+.2f})" for j in order)+'.')
    index=lines.index('\n## Readiness and next decisions');lines[index:index]=extra
    Path(path).write_text('\n'.join(lines)+'\n')


def write_html(analysis,path):
    payload=json.dumps(analysis,allow_nan=False).replace('</','<\\/')
    html='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Colorado 14ers · Phase Four</title>
+<style>*{box-sizing:border-box}body{margin:0;background:#f6f5ef;color:#20352e;font-family:system-ui,sans-serif}main{max-width:1500px;margin:auto;padding:32px}h1{font-size:36px;margin:8px 0}h2{font-size:21px}p{line-height:1.55}small,.muted{color:#596b63}.eyebrow{font-size:12px;letter-spacing:2px;color:#546c5d}.notice{border-left:4px solid #bd843b;background:#fff5e6;padding:13px 18px;margin:20px 0}.controls{display:flex;gap:18px;align-items:end;flex-wrap:wrap;margin:24px 0}label{display:block;font-size:13px}select{display:block;padding:10px;border:1px solid #b9c7bd;border-radius:8px;background:white;font:inherit;margin-top:5px}.cards,.plots{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.cards{grid-template-columns:repeat(4,1fr)}.card,.plot,.panel{background:white;border:1px solid #dce3db;border-radius:12px;padding:16px}.card strong{display:block;font-size:27px}.plot{padding:4px;min-width:0}.chart{height:430px}.two{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin:20px 0}table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:8px;border-bottom:1px solid #e4e9e4}button{padding:9px 13px;border:1px solid #c2d0c6;background:#eef5ef;border-radius:7px;cursor:pointer}.tag{font-size:12px;color:#7a6037}.details{min-height:130px}footer{font-size:12px;margin-top:24px;color:#596b63}@media(max-width:1000px){.plots,.two{grid-template-columns:1fr}.cards{grid-template-columns:repeat(2,1fr)}main{padding:20px}}
+</style><main><div class="eyebrow">COLORADO 14ERS / PHASE FOUR / LOCAL EXPLORATION</div><h1>Three lenses on route difficulty features</h1><p class="muted">PCA explains variation. UMAP and t-SNE explore neighborhoods. None of these maps is a difficulty ranking.</p><div class="notice">Recorded tracks only: approaches and descents are not fully verified. The quality subset excludes every Class 5 route. Switch cohorts to see how that selection changes the picture.</div>
+<div id="highlights" class="controls"></div><div class="controls"><label>Comparison cohort<select id="cohort"><option value="usable_profiles_96" selected>96 tracks · main eleven-feature model</option><option value="observed_segments_100">100 tracks · accepted segments (qualified)</option><option value="numeric_qa_37">37 tracks · numeric QA passes</option><option value="ratings_only_100">100 routes · ratings only</option></select></label><label>Point color<select id="color"><option value="class">Climbing class</option><option value="quality">Numeric QA status</option><option value="extreme">Extreme crux density</option></select></label><label><input id="arrows" type="checkbox"> Show PCA correlation arrows</label><button id="reset">Reset views</button></div>
+<div class="cards"><div class="card"><small>Routes in view</small><strong id="n"></strong></div><div class="card"><small>PC1 + PC2 variance</small><strong id="variance"></strong></div><div class="card"><small>Class 5 routes in view</small><strong id="class5"></strong></div><div class="card"><small>Verified full itineraries</small><strong>0 / 100</strong></div></div>
+<div class="plots" style="margin-top:18px"><div class="plot"><div id="pca" class="chart"></div></div><div class="plot"><div id="umap" class="chart"></div></div><div class="plot"><div id="tsne" class="chart"></div></div></div>
+<div class="two"><section class="panel"><h2>How much survives in two dimensions?</h2><div id="scree" style="height:250px"></div><div id="diagnostics"></div></section><section class="panel details"><h2 id="routeTitle">Inspect a route</h2><p id="routeHint">Hover a point for source features. Click to compare its nearest routes in the standardized input space.</p><div id="routeDetails"></div></section></div>
+<div class="two"><section class="panel"><h2>Reading PCA</h2><p id="pcaRead"></p><div id="loadings"></div><p class="muted">PCA positions are component-SD-normalized correlation-biplot scores. Feature arrows, when enabled, show actual correlations on those axes. Signs are oriented consistently and carry no inherent difficulty meaning.</p></section><section class="panel"><h2>Reading the nonlinear maps</h2><p>Nearby points share input features. Island spacing, shape, size and orientation do not measure difficulty. UMAP settings and t-SNE perplexity can change the map; use the stability results below before reading too much into a cluster.</p><div id="stability"></div><p class="muted">Ratings-only views omit distance, gain and steepness. Different cohorts are fitted separately; their coordinates are not interchangeable.</p></section></div><footer>Fully local and offline · Phase Four 4.0.0 · Feature source 3.0.0 · Seed 42 · No external requests · Full methodology and interpretation in outputs/phase4_report.md</footer></main><script>__PLOTLY__</script><script>const DATA=__DATA__;
+function safe(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}const labels=DATA.labels;let current;
+function draw(){current=DATA.cohorts[document.getElementById('cohort').value];const c=current;document.getElementById('n').textContent=c.count;document.getElementById('variance').textContent=(100*(c.explained_variance_ratio[0]+c.explained_variance_ratio[1])).toFixed(1)+'%';document.getElementById('class5').textContent=c.class_counts['5'];document.getElementById('highlights').replaceChildren();c.rows.forEach((r,i)=>{if(DATA.highlight_route_ids.includes(r.route_id)){let b=document.createElement('button');b.textContent=r.canonical_name;b.onclick=()=>inspect(i);document.getElementById('highlights').appendChild(b);}});let color=document.getElementById('color').value;if(color==='extreme'&&!c.features.some(f=>f.endsWith('crux_density_extreme')))color='class';
+['PCA','UMAP','t-SNE'].forEach((method,j)=>{let e=c[method],values=c.rows.map(r=>color==='class'?+r.yds_class:color==='quality'?(r.profile_qa_pass==='True'?1:0):(r.values.source_track_crux_density_extreme??r.values.observed_segment_crux_density_extreme)),marker={size:10,color:values,colorscale:color==='quality'?[[0,'#b78343'],[1,'#2f7561']]:'Viridis',opacity:.88,line:{color:'#ffffff',width:1},showscale:j===2,colorbar:{thickness:10,title:color==='class'?'Class':color==='quality'?'QA':'Extreme %',tickvals:color==='class'?[1,2,3,4,5]:color==='quality'?[0,1]:undefined,ticktext:color==='quality'?['Review','Pass']:undefined}};
+const hover=c.rows.map(r=>safe(r.canonical_name)+'<br>'+safe(r.route_id)+' · Class '+r.yds_class+'<br>'+c.features.map(f=>safe(labels[f])+': '+r.values[f].toFixed(2)).join('<br>')+'<br>Numeric QA: '+(r.profile_qa_pass==='True'?'pass':'review')+'<br>Accepted recorded distance: '+(100*+r.profile_valid_distance_fraction).toFixed(1)+'%<br>Scope: recorded source track');const trace={type:'scatter',mode:'markers',x:e.coords.map(p=>p[0]),y:e.coords.map(p=>p[1]),text:hover,hovertemplate:'%{text}<extra></extra>',marker,customdata:c.rows.map((r,i)=>i)};
+let annotations=[];if(method==='PCA'&&document.getElementById('arrows').checked){c.features.forEach((f,i)=>{let p=c.correlation_loadings[i];annotations.push({x:p[0],y:p[1],ax:0,ay:0,axref:'x',ayref:'y',text:'',showarrow:true,arrowhead:3,arrowcolor:'#ba7940',arrowwidth:1.5});});}
+const title=method==='PCA'?'PCA · correlation biplot':method==='UMAP'?'UMAP · 15 neighbors / min_dist 0.1':'t-SNE · perplexity 10';let layout={title:{text:title,font:{size:16}},paper_bgcolor:'white',plot_bgcolor:'white',margin:{l:45,r:j===2?75:20,t:55,b:45},hoverlabel:{font:{size:12}},xaxis:{title:method==='PCA'?'PC1 / SD':'Embedding 1',zerolinecolor:'#dee5df',gridcolor:'#eff2ef'},yaxis:{title:method==='PCA'?'PC2 / SD':'Embedding 2',zerolinecolor:'#dee5df',gridcolor:'#eff2ef'},annotations,showlegend:false};let div=document.getElementById(['pca','umap','tsne'][j]);Plotly.react(div,[trace],layout,{responsive:true,displaylogo:false});div.removeAllListeners?.('plotly_click');div.on('plotly_click',ev=>inspect(ev.points[0].customdata));});
+Plotly.react('scree',[{type:'bar',x:c.explained_variance_ratio.map((_,i)=>'PC'+(i+1)),y:c.explained_variance_ratio.map(v=>100*v),marker:{color:'#427563'}}],{margin:{l:45,r:15,t:15,b:40},yaxis:{title:'Variance %'},paper_bgcolor:'white',plot_bgcolor:'white'},{responsive:true,displaylogo:false});
+document.getElementById('diagnostics').innerHTML='<table><tr><th>Method</th><th>Trustworthiness</th><th>5-neighbor overlap</th></tr>'+['PCA','UMAP','t-SNE'].map(m=>'<tr><td>'+m+'</td><td>'+c[m].trustworthiness.toFixed(3)+'</td><td>'+(100*c[m].mean_neighbor_overlap).toFixed(1)+'%</td></tr>').join('')+'</table>';
+document.getElementById('loadings').innerHTML='<table><tr><th>Feature / arrow</th><th>PC1 correlation</th><th>PC2 correlation</th></tr>'+c.features.map((f,i)=>'<tr><td>'+labels[f]+'</td><td>'+c.correlation_loadings[i][0].toFixed(3)+'</td><td>'+c.correlation_loadings[i][1].toFixed(3)+'</td></tr>').join('')+'</table>';
+let top=[0,1].map(axis=>c.features.map((f,i)=>({f,v:c.correlation_loadings[i][axis]})).sort((a,b)=>Math.abs(b.v)-Math.abs(a.v)).slice(0,3).map(o=>labels[o.f]).join(', '));document.getElementById('pcaRead').textContent='PC1 is most associated with '+top[0]+'. PC2 is most associated with '+top[1]+'. These are data-derived associations.';
+document.getElementById('stability').innerHTML='<table><tr><th>Method</th><th>Seed/init agreement</th><th>Setting agreement range</th></tr>'+['UMAP','t-SNE'].map(m=>{let vs=c[m].sensitivity.slice(1).map(v=>v.neighbor_agreement_with_default*100);return '<tr><td>'+m+'</td><td>'+(100*c[m].sensitivity[0].neighbor_agreement_with_default).toFixed(1)+'%</td><td>'+Math.min(...vs).toFixed(1)+'–'+Math.max(...vs).toFixed(1)+'%</td></tr>';}).join('')+'</table>';document.getElementById('routeTitle').textContent='Inspect a route';document.getElementById('routeDetails').innerHTML='';document.getElementById('routeHint').style.display='block';}
+function inspect(i){let c=current,r=c.rows[i],z=c.standardized_features;let nearest=z.map((p,j)=>({j,d:Math.sqrt(p.reduce((s,v,k)=>s+(v-z[i][k])**2,0))})).filter(o=>o.j!==i).sort((a,b)=>a.d-b.d).slice(0,5);document.getElementById('routeTitle').textContent=r.canonical_name;document.getElementById('routeHint').style.display='none';document.getElementById('routeDetails').innerHTML='<p class="tag">'+safe(r.route_id)+' · Class '+r.yds_class+' · Recorded-track scope</p><p>'+safe(r.qa_flags||'No numeric QA flags')+'</p><strong>Nearest in standardized input space</strong><table>'+nearest.map(o=>'<tr><td>'+safe(c.rows[o.j].canonical_name)+'</td><td>'+o.d.toFixed(2)+'</td></tr>').join('')+'</table>';}
+document.getElementById('cohort').onchange=draw;document.getElementById('color').onchange=draw;document.getElementById('arrows').onchange=draw;document.getElementById('reset').onclick=draw;draw();</script></html>'''.replace('\n+','\n')
    Path(path).write_text(html.replace('__PLOTLY__',get_plotlyjs()).replace('__DATA__',payload))


def write_preview(analysis,path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,3,figsize=(15,9),layout='constrained')
    fig.patch.set_facecolor('#f6f5ef')
    for row,key in enumerate(['usable_profiles_96','observed_segments_100']):
        c=analysis['cohorts'][key];classes=np.array([int(r['yds_class']) for r in c['rows']])
        for col,method in enumerate(['PCA','UMAP','t-SNE']):
            ax=axes[row,col];xy=np.array(c[method]['coords'])
            sc=ax.scatter(xy[:,0],xy[:,1],c=classes,cmap='viridis',vmin=1,vmax=5,s=48,edgecolors='white',linewidths=.6)
            ax.set_title(f"{method} · {c['count']} recorded tracks",fontsize=13)
            ax.set_xlabel('PC1 / SD' if method=='PCA' else 'Embedding 1')
            ax.set_ylabel('PC2 / SD' if method=='PCA' else 'Embedding 2')
            ax.grid(alpha=.15);ax.spines[['top','right']].set_visible(False)
            ax.text(.02,.98,f"Trustworthiness {c[method]['trustworthiness']:.3f}",transform=ax.transAxes,va='top',fontsize=9)
    fig.suptitle('Colorado 14er features: PCA, UMAP and t-SNE\nRecorded geometry only · Top: main 96-profile model · Bottom: qualified 100-track accepted-segment model',fontsize=16)
    fig.colorbar(sc,ax=axes,shrink=.7,label='Climbing class',ticks=[1,2,3,4,5])
    fig.savefig(path,dpi=150,facecolor=fig.get_facecolor());plt.close(fig)


def run(project_root=ROOT):
    root=Path(project_root);out=root/'outputs' if (root/'outputs/project_config.json').exists() else root
    config_path=out/'project_config.json';config=json.loads(config_path.read_text())
    feature_path=root/'private_data/routes_features.csv';review_path=out/'phase3_review.json';review=json.loads(review_path.read_text())
    if (review['feature_table_sha256']!=sha(feature_path) or review['manifest_sha256']!=config['manifest_sha256']
        or review['config_sha256']!=sha(config_path)):
        raise ValueError('Phase 3 provenance does not match features/manifest')
    with feature_path.open(newline='') as f:rows=list(csv.DictReader(f))
    if len(rows)!=100 or len({r['route_id'] for r in rows})!=100:raise ValueError('Expected 100 unique routes')
    settings=config['phase4'];features=settings['profile_features'];ratings=settings['ratings_features'];params=settings['parameters']
    cohorts={'numeric_qa_37':([r for r in rows if r['profile_qa_pass']=='True' and all(r[f] for f in features)],features),
             'usable_profiles_96':([r for r in rows if all(r[f] for f in features)],features),
             'ratings_only_100':(rows,ratings),
             'observed_segments_100':([r for r in rows if all(r[f] for f in settings['observed_features'])],settings['observed_features'])}
    data={'embedding_version':VERSION,'scope':settings['scope'],'feature_sha256':sha(feature_path),
          'config_sha256':sha(config_path),'implementation_sha256':sha(out/'block3_embeddings.py'),
          'phase3_review_sha256':sha(review_path),'manifest_sha256':config['manifest_sha256'],
          'parameters':params,'labels':LABELS,'highlight_route_ids':settings['highlight_route_ids'],
          'four_profile_research':settings['four_profile_research'],
          'coverage_cases':[{k:r[k] for k in ('route_id','canonical_name','profile_valid_distance_fraction',
              'observed_segment_crux_density_medium','observed_segment_crux_density_extreme',
              'recorded_chord_crux_density_medium_lower_pct','recorded_chord_crux_density_medium_upper_pct',
              'recorded_chord_crux_density_extreme_lower_pct','recorded_chord_crux_density_extreme_upper_pct')}
              for r in rows if not r['source_track_crux_density_medium']],'runtime':{p:importlib.metadata.version(p) for p in
              ['numpy','scipy','scikit-learn','plotly','umap-learn','numba','llvmlite','pynndescent']},'cohorts':{}}
    with threadpool_limits(limits=1):
        for name,(subset,columns) in cohorts.items():
            print('Computing',name,len(subset),flush=True)
            data['cohorts'][name]=analyze_cohort(subset,columns,params)
    dest=root/'private_data/phase4';dest.mkdir(parents=True,exist_ok=True)
    (dest/'analysis.json').write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
    write_report(data,out/'phase4_report.md');write_html(data,dest/'route_exploration.html');write_preview(data,dest/'phase4_overview.png')
    print(json.dumps({k:{'n':c['count'],'pca_two_variance':sum(c['explained_variance_ratio'][:2]),
                        'umap_trust':c['UMAP']['trustworthiness'],'tsne_trust':c['t-SNE']['trustworthiness']} for k,c in data['cohorts'].items()},indent=2))
    return data


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--project-root',type=Path,default=ROOT)
    run(p.parse_args().project_root)
