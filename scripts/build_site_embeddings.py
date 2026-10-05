"""Publish interpretation of the frozen 103-route fit; never mutate feature/rank inputs."""
import csv
import io
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('embeddings', ROOT/'outputs/block3_embeddings.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
np = m.np
FIELDS = ['gpx_distance_mi','gpx_gain_ft','crux_density_medium','crux_density_extreme',
          'yds_encoded','exposure','rockfall','route_finding','commitment',
          'longest_medium_section_mi','longest_extreme_section_mi']
LABELS = ['Recorded distance','Recorded ascent','20–35% grade density','>35% grade density',
          'Climbing class (encoded)','Exposure','Rockfall','Route finding','Commitment',
          'Longest 20–35% section','Longest >35% section']
RISKS = {s:i for i,s in enumerate(['Low','Moderate','Considerable','High','Extreme'])}


def padded_domain(xy):
    lo, hi = xy.min(axis=0), xy.max(axis=0)
    pad = np.maximum(hi-lo, .1)*.08
    return {'x': [float(lo[0]-pad[0]),float(hi[0]+pad[0])],
            'y': [float(lo[1]-pad[1]),float(hi[1]+pad[1])]}


def build():
    source = ROOT/'site_export/route_features_full.csv'
    audit = json.loads((ROOT/'private_data/site_export_analysis.json').read_text())
    manifest = json.loads((ROOT/'outputs/site_route_manifest.json').read_text())
    identities = {r['route_id']:r for r in manifest}
    rows = {r['route_id']:r for r in csv.DictReader(io.StringIO(source.read_text()))}
    ids = audit['embedding_cohort_ids']
    if len(ids)!=103 or len(set(ids))!=103 or set(rows)!=set(identities):
        raise ValueError('Frozen cohort or manifest identity contract changed; version a new fit explicitly.')
    for method in ['pca','umap','tsne']:
        current = [[float(rows[rid][method+'_x']),float(rows[rid][method+'_y'])] for rid in ids]
        np.testing.assert_allclose(current,audit['coordinates'][method],atol=1e-9)
    x = np.array([[RISKS[r[f]] if f in FIELDS[5:9] else float(r[f]) for f in FIELDS]
                  for r in (rows[i] for i in ids)])
    mean, scale = np.array(audit['feature_mean']), np.array(audit['feature_scale'])
    z = (x-mean)/scale
    v = np.array(audit['pca_components'])
    t = z@v.T
    np.testing.assert_allclose(t, audit['coordinates']['pca'], atol=1e-9)
    np.testing.assert_allclose(z.mean(axis=0), 0, atol=1e-10)
    np.testing.assert_allclose(z.std(axis=0), 1, atol=1e-10)
    d = t.std(axis=0)
    c, f = v.T*d, t/d
    np.testing.assert_allclose(f@c.T, t@v, atol=1e-10)
    lo, hi = m.bootstrap_loadings(x, v, 200, 20261004)
    # Bootstrap helper returns only two axes, aligned to the frozen components.
    near = m.neighbors(z, 5)
    distances = m.pairwise_distances(z)
    routes = []
    for i, rid in enumerate(ids):
        r = rows[rid]
        routes.append({'route_id':rid, 'label':identities[rid]['canonical_name'],
            'primary_peak':identities[rid]['primary_peak'], 'cluster_id':r['cluster_id'],
            'cluster_stability':float(r['cluster_stability']), 'quality_flags':r['quality_flags'],
            'coordinates':{k:audit['coordinates'][k][i] for k in ['pca','umap','tsne']},
            'biplot':f[i].tolist(),
            'pca_representation':float(np.sum(t[i]**2)/np.sum(z[i]**2)),
            'neighbors':[{'route_id':ids[j], 'distance':float(distances[i,j])} for j in near[i]]})
    features = [{'key':key,'label':LABELS[i], 'arrow':c[i].tolist(),
                 'representation':float(np.sum(c[i]**2)),
                 'contribution_pct':(100*v[:,i]**2).tolist(),
                 'bootstrap_low':lo[i].tolist(),'bootstrap_high':hi[i].tolist()}
                for i,key in enumerate(FIELDS)]
    clusters = json.loads((ROOT/'site_export/clusters_summary.json').read_text())
    for cluster in clusters:
        low = cluster['cluster_id'].startswith('lower')
        cluster['display_label'] = 'Lower exposure · simpler navigation' if low else 'Higher exposure · more complex navigation'
        cluster['color'] = '#0072B2' if low else '#D55E00'
        cluster.pop('mean_provisional_score',None)
    xy = {k:np.array(audit['coordinates'][k]) for k in ['pca','umap','tsne']}
    xy['biplot'] = f
    methods = {k:{'domain':padded_domain(a),'metrics':m.metrics(z,a,5)} for k,a in xy.items()}
    linear = x.copy();linear[:,4] = [float(rows[rid]['yds_class']) for rid in ids]
    linear_z = m.StandardScaler().fit_transform(linear)
    ablated = m.StandardScaler().fit_transform(x[:,:9])
    pending = [{'route_id':rid,'label':identities[rid]['canonical_name'],
                'reason':'identity_unresolved' if rid=='co14-107' else 'outside_frozen_103_embedding_fit'}
               for rid in rows if rid not in ids]
    result = {'schema_version':'1.0.0','embedding_version':'103-interpretation-1.0.0',
        'catalog_version':'2.0.0','feature_version':'3.1.1',
        'release_date':'2026-10-04',
        'counts':{'catalog':len(rows),'embedded':len(ids),'ranked':sum(bool(r['provisional_score']) for r in rows.values())},
        'runtime':{'numpy':np.__version__,'sklearn':m.sklearn_version,'scipy':m.scipy.__version__},
        'source_feature_sha256':m.sha(source),'reference_audit_sha256':m.sha(ROOT/'private_data/site_export_analysis.json'),
        'cohort':'frozen_qualified_103','routes':routes,'pending':pending,'features':features,'clusters':clusters,
        'pca':{'explained_variance_ratio':audit['pca_explained_variance_ratio'],
               'full_scree_ratio':(np.linalg.svd(z, compute_uv=False)**2 / np.sum(z*z)).tolist(),
               'axis_labels':['PC1 · Exposure & technical terrain (45.4%)','PC2 · Recorded distance & ascent (21.0%)'],
               'population_score_sd':d.tolist(),
               'biplot_convention':'F=T/D; C=V*D; F C^T equals the rank-two standardized reconstruction. No arrow multiplier.',
               'axis_note':'Biplot axes use unit-SD component scores; ordinary PCA uses original scores.'},
        'methods':methods, 'cluster_candidates':audit['cluster_candidates'],
        'sensitivity':{'linear_class_neighbor_overlap':m.neighbor_agreement(z,linear_z,5),
                       'without_longest_sections_neighbor_overlap':m.neighbor_agreement(z,ablated,5)},
        'methodology':{'neighbor_k':5,'neighbor_space':'Euclidean distance in all eleven reference-standardized features',
          'bootstrap':'200 route resamples, scaler/PCA refitted, axes aligned; seed 20261004; shared-path dependence not corrected',
          'cluster_stability':'Saved 100-resample membership agreement conditional on fixed k=2 and feature representation; not a probability of a true category',
          'scope':'Recorded profiles, including partial itineraries and QA flags. Similarity is not validated difficulty or safety.',
          'nonlinear':'UMAP/t-SNE axes have no physical meaning; islands and between-island distances are not calibrated categories.'}}
    return result


def preview(data):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1,2,figsize=(13,7),gridspec_kw={'width_ratios':[1,1]})
    colors = {c['cluster_id']:c['color'] for c in data['clusters']}
    for cluster in data['clusters']:
        points = np.array([r['biplot'] for r in data['routes'] if r['cluster_id']==cluster['cluster_id']])
        axes[0].scatter(*points.T,s=24,color=cluster['color'],alpha=.8,label=cluster['display_label'])
    for i,feature in enumerate(data['features']):
        a=feature['arrow']
        for ax in axes:
            ax.annotate('',xy=a,xytext=(0,0),arrowprops={'arrowstyle':'->','color':'#444','lw':1})
        offsets={0:(-.13,.13),1:(.01,.03),6:(-.02,.04),7:(.09,-.01)}
        dx,dy=offsets.get(i,(.03,.02))
        axes[1].annotate(str(i+1),xy=a,xytext=(a[0]*1.08+dx,a[1]*1.08+dy),fontsize=10,arrowprops={'arrowstyle':'-','color':'#999','lw':.5})
    axes[1].add_patch(plt.Circle((0,0),1,fill=False,color='#aaa',linestyle='--'))
    for ax in axes:
        ax.axhline(0,color='#ddd',lw=.7);ax.axvline(0,color='#ddd',lw=.7)
        ax.set_aspect('equal');ax.set_xlabel('PC1: exposure & technical terrain');ax.set_ylabel('PC2: recorded distance & ascent')
    axes[0].set_title('Route correlation biplot · 103 profiles')
    axes[0].legend(fontsize=8,loc='upper left',bbox_to_anchor=(0,-.15))
    axes[1].set_xlim(-1.3,1.3);axes[1].set_ylim(-1.3,1.3)
    axes[1].set_title('Feature arrows · magnified view, same correlations')
    fig.text(.52,.03,'\n'.join(f"{i+1:2}. {f['label']}" for i,f in enumerate(data['features'])),fontsize=8)
    fig.text(.04,.08,'First two PCs: 66.4% of variation\nArrows use correlations; no decorative scaling.\nRecorded profiles, not complete-itinerary difficulty.',fontsize=10)
    fig.subplots_adjust(bottom=.32,wspace=.3,top=.91)
    fig.savefig(ROOT/'outputs/site_embeddings_biplot.png',dpi=160)
    plt.close(fig)


if __name__=='__main__':
    with m.threadpool_limits(limits=1):
        result=build()
        (ROOT/'outputs/site_embeddings.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
        preview(result)
    print(json.dumps({'counts':result['counts'],'metrics':{k:v['metrics'] for k,v in result['methods'].items()},'sensitivity':result['sensitivity']},indent=2))
