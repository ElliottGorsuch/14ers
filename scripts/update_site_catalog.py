"""Build the expanded local site catalog; never overwrite frozen Phase 3–6 outputs.

Requires the existing numpy/scipy/scikit-learn/umap and ingestion dependencies.
Only already acquired local files are read. No network or invented measurements.
"""
import csv
import hashlib
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if (ROOT / 'work/phase4_runtime').is_dir():
    sys.path.insert(0, str(ROOT / 'work/phase4_runtime'))
sys.path.insert(0, str(ROOT / 'outputs'))
os.environ.setdefault('NUMBA_NUM_THREADS', '1')
os.environ.setdefault('LOKY_MAX_CPU_COUNT', '1')
def load_analysis_runtime():
    global np, linear_sum_assignment, KMeans, PCA, TSNE, silhouette_score
    global threadpool_limits, UMAP, ingestion, geometry
    import numpy as np
    from scipy.optimize import linear_sum_assignment
    from sklearn.cluster import KMeans
    from sklearn.decomposition import PCA
    from sklearn.manifold import TSNE
    from sklearn.metrics import silhouette_score
    from threadpoolctl import threadpool_limits
    from umap import UMAP
    import block1_scraper as ingestion
    import block2_features as geometry

HEADERS = ('route_id,feature_version,yds_raw,yds_class,yds_encoded,exposure,rockfall,'
           'route_finding,commitment,source_distance_mi,source_gain_ft,gpx_distance_mi,'
           'gpx_gain_ft,crux_density_medium,crux_density_extreme,steep_mileage_mi,'
           'longest_medium_section_mi,longest_extreme_section_mi,pca_x,pca_y,umap_x,'
           'umap_y,tsne_x,tsne_y,cluster_id,cluster_label,cluster_stability,'
           'provisional_rank,provisional_score,provisional_scope,provisional_model,'
           'feature_set,quality_flags').split(',')
FIELD_MAP = {
    'feature_version': 'feature_version', 'yds_raw': 'yds_raw', 'yds_class': 'yds_class',
    'yds_encoded': 'yds_encoded', 'exposure': 'exposure_raw', 'rockfall': 'rockfall_raw',
    'route_finding': 'route_finding_raw', 'commitment': 'commitment_raw',
    'source_distance_mi': 'source_distance_mi', 'source_gain_ft': 'source_gain_ft',
    'gpx_distance_mi': 'source_track_distance_mi', 'gpx_gain_ft': 'source_track_gain_ft',
    'crux_density_medium': 'observed_segment_crux_density_medium',
    'crux_density_extreme': 'observed_segment_crux_density_extreme',
    'steep_mileage_mi': 'source_track_steep_above20_mi',
    'longest_medium_section_mi': 'source_track_longest_medium_mi',
    'longest_extreme_section_mi': 'source_track_longest_extreme_mi',
}


def read_csv(path):
    with path.open(newline='') as handle:
        return list(csv.DictReader(handle))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def profile_components(codes, params, receipts, source_hashes):
    seqs = []
    for code in codes:
        path = ROOT / 'private_data/browser_downloads' / (code + '.gpx')
        if not path.exists():
            return None
        if not any(r.get('gpx_sha256') == sha(path) for r in receipts if r.get('code') == code):
            raise ValueError('Missing/mismatched acquisition receipt: ' + code)
        source_hashes[str(path.relative_to(ROOT))] = sha(path)
        if not geometry.sequences(path.read_bytes()):
            # Old report files can contain waypoints only; never connect them into a hike.
            return None
        ingestion.validate_gpx(path.read_bytes())
        seqs.extend(geometry.sequences(path.read_bytes()))
    if not seqs:
        raise ValueError('No usable track sequences')
    profile, _, qa, _ = geometry.analyze_track(seqs, params)
    flags = ['complete_dry_itinerary_unverified']
    if qa['valid_distance_fraction'] < params['min_valid_distance_fraction']:
        flags.append('insufficient_valid_profile_coverage')
    if any(qa[k] for k in ('near_zero_step', 'long_gap', 'missing_elevation', 'implausible_grade')):
        flags.append('profile_edges_excluded')
    if max(qa['density_medium_range_pp'] or 0, qa['density_extreme_range_pp'] or 0) > params['max_density_sensitivity_pp']:
        flags.append('density_sensitive_to_parameters')
    if (qa['gain_sensitivity_pct'] or 0) > params['max_gain_sensitivity_pct']:
        flags.append('gain_sensitive_to_parameters')
    return profile, qa, flags, seqs


def apply_profile(row, result):
    profile, _, flags, _ = result
    mapping = {'gpx_distance_mi':'distance_mi', 'gpx_gain_ft':'gain_ft',
               'crux_density_medium':'crux_density_medium', 'crux_density_extreme':'crux_density_extreme',
               'steep_mileage_mi':'steep_above20_mi', 'longest_medium_section_mi':'longest_medium_mi',
               'longest_extreme_section_mi':'longest_extreme_mi'}
    row.update({target: profile[source] if profile[source] is not None else '' for target, source in mapping.items()})
    return flags


def export_public_manifest(root=ROOT):
    """Project existing site identity metadata into public Base44 Route records.

    This path never computes features/models or exports coordinates/ratings.
    """
    rows = read_csv(root/'site_export/route_features_full.csv')
    catalog = json.loads((root/'site_export/route_catalog.json').read_text())
    ids = [r['route_id'] for r in rows]
    routes = catalog['routes']
    catalog_ids = [r['route_id'] for r in routes]
    if len(ids) != len(set(ids)) or len(catalog_ids) != len(set(catalog_ids)):
        raise ValueError('Duplicate route ID in feature table or catalog')
    if set(ids) != set(catalog_ids) or catalog['active_count'] != len(ids):
        raise ValueError('Route catalog and feature table do not match')
    if set(ids) & set(catalog['retired_ids']):
        raise ValueError('Retired route in active table')
    by_id = {r['route_id']:r for r in routes}
    records = []
    for row in rows:
        entry = by_id[row['route_id']]
        for ready, fields in [('plot_ready', ('pca_x','pca_y','umap_x','umap_y','tsne_x','tsne_y')),
                              ('rank_ready', ('provisional_rank','provisional_score'))]:
            populated = [row[f] != '' for f in fields]
            if any(populated) != all(populated) or entry[ready] != all(populated):
                raise ValueError('Readiness disagrees with features: '+row['route_id'])
        if entry['primary_peak'] not in entry['summits']:
            raise ValueError('Primary peak missing from summit associations')
        value = row['yds_class']
        yds = int(value) if value else None
        if yds is not None and yds not in range(1,6):
            raise ValueError('Invalid climbing class')
        # Explicit allowlist excludes recorded coordinates, derived similarity,
        # model outputs, community records and acquisition receipts.
        record = {k:entry[k] for k in ('route_id','canonical_name','primary_peak','summits',
                  'source_url','source_kind','identity_status','catalog_status',
                  'geometry_scope','complete_itinerary_verified','plot_ready','rank_ready','voting_ready')}
        record.update(catalog_version=catalog['catalog_version'], feature_version=row['feature_version'],
                      yds_class=yds, scope_note=entry.get('scope_note',''))
        records.append(record)
    for peak in ('Mt. Cameron','Mt. Lincoln'):
        if [r['route_id'] for r in records if peak in r['summits']] != ['co14-066']:
            raise ValueError('Cameron/Lincoln must occur only in Decalibron')
    destination = root/'outputs/site_route_manifest.json'
    temporary = destination.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(records, indent=2, allow_nan=False)+'\n')
    temporary.replace(destination)
    return {'routes':len(records), 'plot_ready':sum(r['plot_ready'] for r in records),
            'pending_ids':[r['route_id'] for r in records if not r['plot_ready']],
            'retired_ids':catalog['retired_ids']}


def main():
    load_analysis_runtime()
    source_paths = [ROOT/p for p in ('outputs/route_manifest.csv', 'outputs/project_config.json',
                    'outputs/site_route_additions.json', 'private_data/routes_features.csv',
                    'private_data/phase5/evaluation.json')]
    source_hashes = {str(p.relative_to(ROOT)):sha(p) for p in source_paths}
    decisions = json.loads(source_paths[2].read_text())
    config = json.loads(source_paths[1].read_text())
    params = config['phase3']['parameters']
    model = json.loads(source_paths[4].read_text())['final_models']['observed_segments_100']
    manifest = read_csv(source_paths[0])
    features = {r['route_id']:r for r in read_csv(source_paths[3])}
    receipts = json.loads((ROOT/'private_data/browser_downloads/download_ledger.json').read_text())
    risks = config['feature_contract']['risk_encoding']
    rows, catalog, vectors, profile_audit = [], [], {}, {}
    for route in manifest:
        rid = route['route_id']
        if rid in decisions['retired_ids']:
            continue
        source = features[rid]
        row = {h:'' for h in HEADERS}
        row['route_id'] = rid
        row.update({target:source[origin] for target,origin in FIELD_MAP.items()})
        row['quality_flags'] = source['qa_flags'].replace('|', ',')
        vector = [float(source[f]) for f in model['features']]
        vectors[rid] = vector
        summits = list(dict.fromkeys(route['summit_order'].split('|')))
        entry = {'route_id':rid, 'canonical_name':route['canonical_name'],
                 'primary_peak':decisions['primary_peak_overrides'].get(rid, route['required_summit'] or summits[-1]),
                 'summits':summits, 'source_url':route['source_url'], 'source_kind':'official_overview',
                 'identity_status':'verified', 'geometry_scope':'recorded_source_track',
                 'complete_itinerary_verified':False, 'catalog_status':'recorded_profile_with_qa'}
        seqs = geometry.sequences((ROOT/'private_data/raw/gpx'/f'{rid}.gpx').read_bytes())
        if rid == 'co14-025':
            result = profile_components(['shav1','tabe2'],params,receipts,source_hashes)
            if result is None:
                raise ValueError('Tabeguache repair requires both acquired components')
            flags = apply_profile(row,result)
            flags.extend(['component_assembly','return_geometry_unverified'])
            row['quality_flags'] = ','.join(flags)
            vector[:4] = [row['gpx_distance_mi'],row['gpx_gain_ft'],row['crux_density_medium'],row['crux_density_extreme']]
            vector[-2:] = [row['longest_medium_section_mi'],row['longest_extreme_section_mi']]
            vectors[rid] = vector
            seqs = result[3]
            entry['geometry_scope'] = 'Shavano_ascent_and_Tabeguache_connector_separate_segments'
            entry['scope_note'] = 'Both recorded ascent components included; 3.04 m join is not interpolated and return is not fabricated.'
            profile_audit[rid] = {'components':['shav1','tabe2'],'qa':result[1]}
        entry['recorded_start'] = {'lat':seqs[0][0][0],'lon':seqs[0][0][1]}
        rows.append(row)
        catalog.append(entry)

    for route in decisions['routes']:
        rid = route['route_id']
        row = {h:'' for h in HEADERS}
        row.update(route_id=rid,feature_version=geometry.FEATURE_VERSION)
        flags = ['metadata_scope_pending','complete_dry_itinerary_unverified']
        entry = {k:route[k] for k in ('route_id','canonical_name','primary_peak','summits','source_url','source_kind')}
        entry.update(identity_status='pending' if route['source_kind']=='unverified_request' else 'verified',
                     geometry_scope='unavailable',complete_itinerary_verified=False,
                     scope_note=route['metric_scope'],catalog_status='pending_measurements')
        if route['source_kind'] == 'unverified_request':
            flags.append('identity_unverified')
        for field in ('source_distance_mi','source_gain_ft'):
            row[field] = route.get(field,'')
        if route.get('yds_class'):
            row.update(yds_raw=route['yds_raw'],yds_class=route['yds_class'],
                       yds_encoded=config['yds_encoding'][str(route['yds_class'])])
        code = route.get('code')
        if route['source_kind'] == 'official_overview':
            html_path = ROOT/'private_data/browser_downloads'/f'{code}_metadata.html'
            if not html_path.exists():
                raise ValueError('Acquire official overview before exporting '+rid)
            html_hash = sha(html_path)
            if not any(r.get('metadata_sha256') == html_hash for r in receipts if r.get('code') == code):
                raise ValueError('Overview receipt does not match '+rid)
            source_hashes[str(html_path.relative_to(ROOT))] = html_hash
            parsed = ingestion.parse_route(html_path.read_bytes(),route['source_url'])
            for field in ('yds_raw','yds_class','yds_encoded'):
                row[field] = parsed[field] if parsed[field] is not None else ''
            for risk in geometry.RISKS:
                row[risk] = parsed[risk+'_raw'] or ''
            # Explicit variant selection must equal an actual captured candidate.
            for field in ('source_distance_mi','source_gain_ft'):
                if row[field] != '' and row[field] not in [v['value'] for v in parsed[field+'_candidates']]:
                    raise ValueError('Published metric is not in captured overview: '+rid+' '+field)
            flags.remove('metadata_scope_pending')
        result = profile_components([code],params,receipts,source_hashes) if code else None
        if result is None:
            flags.append('matching_gpx_pending')
        else:
            flags.extend(apply_profile(row,result))
            entry['geometry_scope'] = 'recorded_source_track'
            entry['recorded_start'] = {'lat':result[3][0][0][0],'lon':result[3][0][0][1]}
            profile_audit[rid] = {'components':[code],'qa':result[1]}
        row['quality_flags'] = ','.join(dict.fromkeys(flags))
        vector_fields = ['gpx_distance_mi','gpx_gain_ft','crux_density_medium','crux_density_extreme','yds_encoded',
                         'exposure','rockfall','route_finding','commitment','longest_medium_section_mi','longest_extreme_section_mi']
        if all(row[f] != '' for f in vector_fields):
            vectors[rid] = [float(row[f]) if f not in risks_fields() else float(risks[row[f]]) for f in vector_fields]
            entry['catalog_status'] = 'recorded_profile_with_qa'
        rows.append(row)
        catalog.append(entry)

    ids = [r['route_id'] for r in rows]
    if len(ids) != len(set(ids)) or set(ids) & set(decisions['retired_ids']):
        raise ValueError('Duplicate or retired route ID')
    for peak in ('Mt. Lincoln','Mt. Cameron'):
        if [e['route_id'] for e in catalog if peak in e['summits']] != ['co14-066']:
            raise ValueError('Cameron/Lincoln may be associated only with Decalibron')
    eligible = [rid for rid in ids if rid in vectors]
    raw = np.array([vectors[rid] for rid in eligible],dtype=float)
    if not np.isfinite(raw).all():
        raise ValueError('Non-finite feature vector')
    mean, scale = raw.mean(axis=0),raw.std(axis=0)
    scale[scale==0] = 1
    z = (raw-mean)/scale
    candidates, fits = [],{}
    with threadpool_limits(limits=1):
        pca = PCA(n_components=2,svd_solver='full')
        coordinates = {'pca':pca.fit_transform(z),
                       'umap':UMAP(n_neighbors=15,min_dist=.1,random_state=42,n_jobs=1).fit_transform(z),
                       'tsne':TSNE(n_components=2,perplexity=10,max_iter=1500,random_state=42,init='pca',learning_rate='auto').fit_transform(z)}
        for k in range(2,7):
            fit = KMeans(n_clusters=k,n_init=50,random_state=42,algorithm='lloyd').fit(z)
            sizes = np.bincount(fit.labels_,minlength=k)
            candidates.append({'k':k,'silhouette':float(silhouette_score(z,fit.labels_)),'sizes':sizes.tolist(),'eligible':bool(sizes.min()>=5)})
            fits[k] = fit
        selected = max((c for c in candidates if c['eligible']),key=lambda c:(c['silhouette'],-c['k']))
        fit = fits[selected['k']]
        if selected['k'] != 2:
            raise ValueError('Review cluster names before exporting a changed partition')
        labels = fit.labels_
        agreement = np.zeros(len(eligible))
        rng = np.random.default_rng(20261001)
        for b in range(100):
            sampled = rng.integers(0,len(z),size=len(z))
            boot = KMeans(n_clusters=2,n_init=50,random_state=42+b).fit(z[sampled])
            predicted = boot.predict(z)
            overlap = np.zeros((2,2),dtype=int)
            np.add.at(overlap,(labels,predicted),1)
            baseline,resampled = linear_sum_assignment(-overlap)
            aligned = np.array([dict(zip(resampled,baseline))[v] for v in predicted])
            agreement += aligned==labels
        agreement /= 100
    order = sorted(range(2),key=lambda label:float(z[labels==label,model['features'].index('route_finding_encoded')].mean()))
    cluster_names = [('lower_exposure_navigation','Lower exposure and route-finding ratings'),
                     ('higher_exposure_navigation','Higher exposure and route-finding ratings')]
    cluster_meta = {label:cluster_names[n] for n,label in enumerate(order)}
    weights = np.array(model['BT_linear']['weights'],dtype=float)
    scores = ((raw-np.array(model['scaler_mean']))/np.array(model['scaler_scale'])) @ weights
    score_map = dict(zip(eligible,scores.tolist()))
    rank_ids = sorted(eligible,key=lambda rid:(-score_map[rid],rid))
    rank_map = {rid:i+1 for i,rid in enumerate(rank_ids)}
    indices = {rid:i for i,rid in enumerate(eligible)}
    for row,entry in zip(rows,catalog):
        rid = row['route_id']
        entry.update(plot_ready=rid in indices,rank_ready=rid in indices,voting_ready=False,
                     community_elo=1500,community_votes=0)
        if rid not in indices:
            continue
        i = indices[rid]
        for method,coords in coordinates.items():
            row[method+'_x'],row[method+'_y'] = coords[i].tolist()
        row.update(cluster_id=cluster_meta[labels[i]][0],cluster_label=cluster_meta[labels[i]][1],
                   cluster_stability=float(agreement[i]),provisional_rank=rank_map[rid],
                   provisional_score=score_map[rid],provisional_scope=f'qualified_expanded_{len(eligible)}_reference_fit',
                   provisional_model='linear_btl',feature_set='eleven_features')
        distances = np.linalg.norm(z-z[i],axis=1)
        neighbors = [j for j in np.argsort(distances) if j!=i][:5]
        entry['similar_routes'] = [{'route_id':eligible[j],'standardized_distance':float(distances[j]),
                                   'shared_features':[model['features'][t] for t in np.argsort(np.abs(z[j]-z[i]))[:3]]}
                                  for j in neighbors]
    summaries = []
    for label in order:
        members = np.where(labels==label)[0]
        centroid = z[members].mean(axis=0)
        dominant = np.argsort(-np.abs(centroid),kind='stable')[:4]
        summaries.append({'cluster_id':cluster_meta[label][0],'cluster_label':cluster_meta[label][1],
                          'size':len(members),'mean_provisional_score':float(scores[members].mean()),
                          'stability':float(agreement[members].mean()),
                          'dominant_features':[{'feature':model['features'][j],'mean_standardized_value':float(centroid[j]),
                                               'direction':'above_cohort_mean' if centroid[j]>0 else 'below_cohort_mean'} for j in dominant]})
    pending = [e['route_id'] for e in catalog if not e['plot_ready']]
    assert sum(s['size'] for s in summaries)==len(eligible)
    stamp = datetime.now(timezone.utc).isoformat(timespec='seconds')
    audit = {'catalog_version':decisions['catalog_version'],'timestamp':stamp,'rows':len(rows),
             'feature_version':geometry.FEATURE_VERSION,'embedding_cohort_ids':eligible,
             'feature_names':model['features'],'feature_mean':mean.tolist(),'feature_scale':scale.tolist(),
             'pca_components':pca.components_.tolist(),'pca_explained_variance_ratio':pca.explained_variance_ratio_.tolist(),
             'coordinates':{k:v.tolist() for k,v in coordinates.items()},'cluster_candidates':candidates,
             'selected_k':2,'bootstrap_resamples':100,'bootstrap_seed':20261001,'plot_seed':42,
             'profile_qa':profile_audit,'pending_ids':pending,'source_sha256':source_hashes,
             'base44_import_ready':True,'complete_difficulty_dataset_ready':False}
    dest = ROOT/'site_export'
    dest.mkdir(exist_ok=True)
    temporary = dest/'route_features_full.csv.tmp'
    with temporary.open('w',newline='') as handle:
        writer = csv.DictWriter(handle,fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)
    saved = read_csv(temporary)
    assert len(saved)==len(rows) and {r['route_id'] for r in saved}==set(ids)
    temporary.replace(dest/'route_features_full.csv')
    for name,value in [('clusters_summary.json',summaries),('route_catalog.json',
                       {'catalog_version':decisions['catalog_version'],'retired_ids':decisions['retired_ids'],
                        'active_count':len(rows),'plot_count':len(eligible),'pending_ids':pending,'routes':catalog})]:
        (dest/name).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
    (ROOT/'private_data/site_export_analysis.json').write_text(json.dumps(audit,indent=2,allow_nan=False)+'\n')
    provenance = (f'Exported {stamp}; catalog_version {decisions["catalog_version"]}, feature_version {geometry.FEATURE_VERSION}; '
        f'{len(rows)} catalog rows including {len(pending)} pending entries, {len(eligible)} complete eleven-feature recorded-profile vectors. '
        'Frozen Phase Three–Six inputs are unchanged. New profiles use the existing segment-safe 20–35% medium and >35% extreme grade method; '
        'crux densities are accepted-recorded-segment percentages, not complete-route observations. Tabeguache now includes separate Shavano ascent '
        'and Tabeguache connector sequences; no bridge or reverse return was invented. Full-approach published metrics retain their explicit start variants. '
        'PCA (raw component scores), UMAP (15 neighbors, min_dist 0.1) and t-SNE (perplexity 10, PCA initialization, 1500 iterations) '
        'were recomputed together on the expanded complete-vector cohort using seed 42; do not mix these coordinates with older plot exports. '
        'KMeans uses that standardized eleven-feature space, n_init 50, seed 42, k=2 selected by maximum eligible silhouette among k=2..6 '
        'with minimum group size 5. Row stability is per-route reassignment agreement over 100 bootstrap samples, seed 20261001, '
        'with Hungarian label alignment; summary stability is its member mean, conditional on this representation and k. '
        'Provisional model linear_btl uses the saved Phase Five qualified_100 scaler and linear coefficients without retraining; '
        'scores are reference-model projections and ranks sort only the eligible expanded cohort. This synthetic-teacher model has no human validation. '
        'Rows with missing risk/geometry or unresolved identity keep blank plots, clusters and rankings; missing values are empty CSV cells, never zero imputations. '
        'Community Elo is neutral 1500 with no votes; expanded IDs are not yet enabled in the frozen 100-route voting service. '
        'route_catalog.json supplies names, primary peak, all summit associations, pending status, nearest neighbors and recorded-start coordinates '
        '(recorded starts are not necessarily full trailhead or summit locations). No raw GPX, cookies or download receipts are exported. '
        'Source hashes and detailed QA are retained privately in private_data/site_export_analysis.json. '
        'The catalog is an expansion of requested summer itineraries, not every possible 14er route.\n')
    (dest/'PROVENANCE.md').write_text(provenance)
    assert all(sha(ROOT/path)==value for path,value in source_hashes.items()), 'Source changed during export'
    summary = {'rows':len(rows),'columns':len(HEADERS),'plotted_ranked':len(eligible),'pending_ids':pending,
               'null_per_column':{h:sum(r[h]=='' for r in saved) for h in HEADERS},
               'clusters':[{k:s[k] for k in ('cluster_id','size','stability')} for s in summaries]}
    summary["public_manifest"] = export_public_manifest()
    print(json.dumps(summary,indent=2))


def risks_fields():
    return ('exposure','rockfall','route_finding','commitment')


if __name__=='__main__':
    if sys.argv[1:] == ['--manifest-only']:
        print(json.dumps(export_public_manifest(), indent=2))
    elif sys.argv[1:]:
        raise SystemExit('Usage: update_site_catalog.py [--manifest-only]')
    else:
        main()
