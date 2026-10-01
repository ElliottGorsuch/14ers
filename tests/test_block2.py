"""Analytical geometry tests plus private real-snapshot invariants when available."""
import csv
import importlib.util
import json
import math
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('features', ROOT/'outputs/block2_features.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
PARAMS = json.loads((ROOT/'outputs/project_config.json').read_text())['phase3']['parameters']


def profile(positions, elevations):
    return [(39+x/6371008.8*180/math.pi, -106, z) for x, z in zip(positions, elevations)]


class Tests(unittest.TestCase):
    def test_accepted_density_bounds_do_not_impute_excluded_chords(self):
        profile={'crux_density_medium':30.0,'crux_density_extreme':40.0}
        result=m.accepted_segment_densities(profile,{'valid_distance_fraction':.9})
        self.assertEqual(result['observed_segment_crux_density_medium'],30)
        self.assertAlmostEqual(result['recorded_chord_crux_density_medium_lower_pct'],27)
        self.assertAlmostEqual(result['recorded_chord_crux_density_medium_upper_pct'],37)
        self.assertAlmostEqual(result['recorded_chord_crux_density_extreme_lower_pct'],36)
        self.assertAlmostEqual(result['recorded_chord_crux_density_extreme_upper_pct'],46)
        complete=m.accepted_segment_densities(profile,{'valid_distance_fraction':1.0})
        self.assertEqual(complete['recorded_chord_crux_density_medium_lower_pct'],30)
        self.assertEqual(complete['recorded_chord_crux_density_medium_upper_pct'],30)
        missing=m.accepted_segment_densities({'crux_density_medium':None,'crux_density_extreme':None},{'valid_distance_fraction':0})
        self.assertIsNone(missing['observed_segment_crux_density_extreme'])

    def test_distance_weighted_bands_and_exact_boundaries(self):
        params = dict(PARAMS)
        result = m.summarize_edges([(np.array([10., 20., 30., 40.]),
                                     np.array([2., 7., 12., 0.]))], params)
        self.assertAlmostEqual(result['crux_density_medium'], 30)
        self.assertAlmostEqual(result['crux_density_extreme'], 30)
        self.assertAlmostEqual(result['steep_above20_mi']*m.M_PER_MILE, 60)
        self.assertAlmostEqual(result['gain_ft']/m.FT_PER_M, 21)
        self.assertAlmostEqual(result['longest_above20_mi']*m.M_PER_MILE, 60)

    def test_percent_grade_is_not_degrees(self):
        result = m.summarize_edges([(np.array([100.]), np.array([25.]))], PARAMS)
        self.assertEqual(result['crux_density_medium'], 100)
        self.assertEqual(result['crux_density_extreme'], 0)
        self.assertLess(math.degrees(math.atan(.25)), 20)

    def test_constant_slope_resampling_smoothing_and_reverse(self):
        seq = profile([0, 50, 100, 200, 250], [3000, 3020, 3040, 3080, 3100])
        result, raw, qa, _ = m.analyze_track([seq], PARAMS)
        self.assertAlmostEqual(result['gain_ft'], 100*m.FT_PER_M)
        self.assertAlmostEqual(result['crux_density_extreme'], 100)
        self.assertAlmostEqual(qa['density_extreme_range_pp'], 0)
        reverse, _, _, _ = m.analyze_track([seq[::-1]], PARAMS)
        self.assertAlmostEqual(reverse['crux_density_extreme'], result['crux_density_extreme'])
        self.assertAlmostEqual(reverse['gain_ft'], 0)

    def test_sequence_boundaries_do_not_join_or_extend_crux(self):
        a = profile([0, 50, 100], [3000, 3020, 3040])
        b = profile([10000, 10050, 10100], [4000, 4020, 4040])
        result, _, qa, _ = m.analyze_track([a, b], PARAMS)
        self.assertAlmostEqual(qa['recorded_distance_m'], 200)
        self.assertAlmostEqual(result['longest_extreme_mi']*m.M_PER_MILE, 100)
        self.assertAlmostEqual(result['crux_extreme_mi']*m.M_PER_MILE, 200)

    def test_gaps_missing_elevation_and_vertical_duplicate_split_runs(self):
        seq = profile([0, 50, 1000, 1050, 1050, 1100, 1150],
                      [3000, 3020, 3200, 3220, 3300, None, 3340])
        runs, qa = m.validated_runs([seq], PARAMS)
        self.assertEqual(qa['long_gap'], 1)
        self.assertEqual(qa['near_zero_step'], 1)
        self.assertEqual(qa['missing_elevation'], 2)
        self.assertEqual(len(runs), 2)
        result = m.summarize_edges(m.profile_edges(runs, 10, 25), PARAMS)
        self.assertAlmostEqual(result['gain_ft']/m.FT_PER_M, 40)
        self.assertAlmostEqual(result['longest_extreme_mi']*m.M_PER_MILE, 50)

    def test_spike_not_smoothed_into_valid_feature(self):
        seq = profile([0, 10, 20, 30], [3000, 3100, 3000, 3001])
        _, _, qa, _ = m.analyze_track([seq], PARAMS)
        self.assertEqual(qa['implausible_grade'], 2)
        self.assertLess(qa['valid_distance_fraction'], .95)

    def test_flat_and_unusable_profiles(self):
        flat, _, qa, _ = m.analyze_track([profile([0, 50, 100], [3000]*3)], PARAMS)
        self.assertEqual(flat['gain_ft'], 0)
        self.assertEqual(flat['crux_density_extreme'], 0)
        self.assertIsNone(qa['gain_sensitivity_pct'])
        empty, _, qa, _ = m.analyze_track([profile([0, 0], [3000, 4000])], PARAMS)
        self.assertIsNone(empty['crux_density_medium'])
        self.assertEqual(qa['valid_distance_fraction'], 0)

    def test_consecutive_crux_breaks_on_gentle_section(self):
        result = m.summarize_edges([(np.array([100., 50., 80.]), np.array([50., 0., 40.]))], PARAMS)
        self.assertAlmostEqual(result['crux_extreme_mi']*m.M_PER_MILE, 180)
        self.assertAlmostEqual(result['longest_extreme_mi']*m.M_PER_MILE, 100)

    def test_overlap_screen_reversals_and_transitive_prior_groups(self):
        seq = profile([0, 50, 100], [3000, 3010, 3020])
        cells = m.occupied_cells([seq], 50)
        self.assertEqual(cells, m.occupied_cells([seq[::-1]], 50))
        groups, links = m.evaluation_groups([
            {'route_id':'a', 'evaluation_group':'a|b'}, {'route_id':'b'}, {'route_id':'c'}, {'route_id':'d'}],
            {'a':{(0,0)}, 'b':{(1,1)}, 'c':{(1,1)}, 'd':{(9,9)}}, .5)
        self.assertEqual(groups['a'], 'a|b|c')
        self.assertEqual(groups['d'], 'd')
        self.assertEqual(len(links), 1)

    @unittest.skipUnless((ROOT/'private_data/routes_features.csv').exists(), 'private real-data snapshot unavailable')
    def test_real_features_units_bounds_and_scope_gates(self):
        with (ROOT/'private_data/routes_features.csv').open(newline='') as f:
            rows = list(csv.DictReader(f))
        report = json.loads((ROOT/'outputs/phase3_review.json').read_text())
        self.assertEqual(len(rows), 100)
        self.assertEqual(len({r['route_id'] for r in rows}), 100)
        self.assertEqual(m.digest(ROOT/'private_data/routes_features.csv'), report['feature_table_sha256'])
        for row in rows:
            self.assertEqual(int(row['yds_encoded']), 2**(int(row['yds_class'])-1))
            for risk in m.RISKS:
                self.assertEqual(int(row[risk+'_encoded']),
                                 {'Low':0,'Moderate':1,'Considerable':2,'High':3,'Extreme':4}[row[risk+'_raw']])
            if row['feature_eligible'] != 'True':
                self.assertTrue(all(row[k] == '' for k in m.GEOMETRY_FEATURES))
            if row['source_track_crux_density_medium']:
                med, ext = float(row['source_track_crux_density_medium']), float(row['source_track_crux_density_extreme'])
                self.assertTrue(0 <= med <= 100 and 0 <= ext <= 100 and med+ext <= 100+1e-8)
            for band in ('medium','extreme'):
                density=float(row['observed_segment_crux_density_'+band])
                lower=float(row['recorded_chord_crux_density_'+band+'_lower_pct'])
                upper=float(row['recorded_chord_crux_density_'+band+'_upper_pct'])
                self.assertTrue(0<=lower<=density<=upper<=100)
            self.assertLessEqual(float(row['source_track_longest_extreme_mi']), float(row['source_track_crux_extreme_mi'])+1e-8)
        self.assertEqual(report['class_and_risk_encodings_complete'], 100)
        self.assertFalse(report['phase3_dataset_ready'])

    @unittest.skipUnless((ROOT/'private_data/raw').exists(), 'private real-data snapshot unavailable')
    def test_source_rating_tamper_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            shutil.copytree(ROOT/'private_data/raw', folder/'raw')
            path = folder/'raw/route_status.csv'
            with path.open(newline='') as f:
                reader = csv.DictReader(f); fields = reader.fieldnames; rows = list(reader)
            rows[0]['exposure_raw'] = 'Extreme'
            with path.open('w', newline='') as f:
                writer = csv.DictWriter(f, fields); writer.writeheader(); writer.writerows(rows)
            with self.assertRaisesRegex(ValueError, 'altered source risk'):
                m.run_features(ROOT, folder/'raw', folder/'features.csv', folder/'review.json')
            self.assertFalse((folder/'features.csv').exists())

    @unittest.skipUnless((ROOT/'private_data/raw').exists(), 'private real-data snapshot unavailable')
    def test_reviewed_export_releases_only_verified_geometry_features(self):
        # Synthetic full out-and-back replaces just the first private fixture row.
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            shutil.copytree(ROOT/'private_data/raw', folder/'raw')
            points = profile(list(range(0, 501, 50))+list(range(450, -1, -50)),
                             [3000+x*.1 for x in range(0, 501, 50)]+[3000+x*.1 for x in range(450, -1, -50)])
            body = ('<gpx><trk><trkseg>'+''.join(f'<trkpt lat="{lat}" lon="{lon}"><ele>{z}</ele></trkpt>'
                    for lat, lon, z in points)+'</trkseg></trk></gpx>').encode()
            path = folder/'raw/route_status.csv'
            with path.open(newline='') as f:
                reader = csv.DictReader(f); fields = reader.fieldnames; rows = list(reader)
            result, _, _, _ = m.analyze_track([points], PARAMS)
            # Use the existing ingestion validator to bind every geometric diagnostic.
            ingestion_spec=importlib.util.spec_from_file_location('fixture_ingestion',ROOT/'outputs/block1_scraper.py')
            ingestion=importlib.util.module_from_spec(ingestion_spec); ingestion_spec.loader.exec_module(ingestion)
            quality = ingestion.validate_gpx(body)
            row = rows[0]
            row.update(ingestion_method='approved_local_export', itinerary_verified='true',
                       dry_summer_verified='true', training_eligible='True', metadata_complete='True',
                       source_distance_mi=str(result['distance_mi']), source_gain_ft=str(result['gain_ft']))
            for key, value in quality.items():
                if key in fields:
                    row[key] = value if not isinstance(value, list) else json.dumps(value)
            sidecar = {k: row[k] for k in ('route_id','start_policy','summit_order','descent_policy','yds_raw')}
            sidecar.update(**quality, reviewer='Synthetic fixture reviewer', review_date='2026-09-30',
                           metadata_evidence='Synthetic fixture only', geometry_evidence='Synthetic full out-and-back',
                           conditions_evidence='Synthetic fixture only', permission_evidence='Synthetic test permission',
                           source_references=[row['source_url']], export_sha256='fixture-export-hash',
                           itinerary_verified=True, dry_summer_verified=True, yds_class=int(float(row['yds_class'])),
                           source_distance_mi=result['distance_mi'], source_gain_ft=result['gain_ft'])
            sidecar.update({r+'_raw': row[r+'_raw'] for r in m.RISKS})
            (folder/'raw/gpx/co14-001.gpx').write_bytes(body)
            (folder/'raw/gpx/co14-001.json').write_text(json.dumps(sidecar))
            with path.open('w', newline='') as f:
                writer = csv.DictWriter(f, fields); writer.writeheader(); writer.writerows(rows)
            summary_path=folder/'raw/run_summary.json'; summary=json.loads(summary_path.read_text())
            summary['training_eligible']=1; summary_path.write_text(json.dumps(summary))
            review=m.run_features(ROOT,folder/'raw',folder/'features.csv',folder/'review.json')
            self.assertEqual(review['feature_eligible_count'],1)
            with (folder/'features.csv').open(newline='') as f:
                featured=list(csv.DictReader(f))
            self.assertEqual(featured[0]['feature_scope'],'complete_reviewed_itinerary')
            self.assertTrue(featured[0]['distance_mi'])
            self.assertEqual(featured[1]['distance_mi'],'')


if __name__ == '__main__':
    unittest.main()
