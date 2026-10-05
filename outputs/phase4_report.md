# Phase Four: PCA, UMAP and t-SNE exploration

The three methods are built and run locally on real Phase Three features. This is **recorded-track exploration**, not a complete-itinerary difficulty ranking. No data is published or sent to an external analysis service.

## What to open

Open `private_data/phase4/route_exploration.html` in Codex for all three plots. Select the cohort and color, hover for route/feature details, and click a route to see its five nearest neighbors in the standardized input space. PCA offers true correlation loading arrows and a scree plot. The page is self-contained, including Plotly; it works offline.

`private_data/phase4/phase4_overview.png` is the static comparison. `private_data/phase4/analysis.json` saves coordinates, scaler mean/scale, PCA components/loadings, bootstrap intervals, input features, parameters, diagnostics and provenance. Together these support reproducible exploration without additional pickle artifacts.

## Cohorts and selection bias

| View | Routes | Inputs | Interpretation |
|---|---:|---|---|
| Numeric QA subset | 37 | Eleven profile/class/risk features | Recorded profiles passing the current numeric checks; dry full-itinerary scope still unverified |
| All usable profiles | 96 | Same eleven features | Exploratory comparison that includes sensitivity/gap flags; four missing-density rows excluded |
| Accepted-segment comparison | 100 | Eleven features using accepted-segment densities | Includes four sub-95% profiles; observational scope and excluded-length bounds explicit |
| Ratings only | 100 | Class plus four risk encodings | Full-roster comparison independent of GPX coverage; no endurance or steepness inputs |

The numeric-QA subset contains **no Class 5 routes**, so it underrepresents the most technical end of the cohort. The usable-profile view has 4 Class 5 routes. Results that differ between these views can reflect selection bias as well as quality. Each view gets its own fitted scaler and embeddings; axes cannot be compared numerically across views. No profile is imputed.

## PCA findings

| Cohort | PC1 | PC2 | First two combined |
|---|---:|---:|---:|
| numeric_qa_37 | 40.2% | 19.3% | 59.5% |
| usable_profiles_96 | 47.5% | 20.6% | 68.1% |
| ratings_only_100 | 80.8% | 8.9% | 89.7% |
| observed_segments_100 | 46.9% | 21.0% | 67.9% |

PCA was fitted after population standardization, without whitening. Components are oriented by their largest coefficient for reproducible presentation; a sign flip changes neither fit nor meaning. The correlation biplot divides scores by each component's population SD and draws feature-score correlations on the same axes. Neighbor metrics use those displayed coordinates.

For the broader 96-track cohort, feature-score correlations are:

| Feature | PC1 | PC2 | PC1 bootstrap 95% range | PC2 bootstrap 95% range |
|---|---:|---:|---|---|
| Recorded distance | -0.254 | +0.927 | -0.52 to +0.12 | +0.80 to +0.97 |
| Recorded gain | -0.209 | +0.879 | -0.51 to +0.18 | +0.74 to +0.92 |
| Medium crux density | -0.485 | -0.497 | -0.64 to -0.34 | -0.70 to -0.22 |
| Extreme crux density | +0.767 | -0.330 | +0.55 to +0.86 | -0.60 to -0.13 |
| Class encoding | +0.848 | -0.119 | +0.79 to +0.89 | -0.27 to +0.02 |
| Exposure | +0.925 | +0.035 | +0.90 to +0.95 | -0.12 to +0.13 |
| Rockfall | +0.865 | +0.124 | +0.83 to +0.91 | -0.08 to +0.27 |
| Route finding | +0.905 | +0.175 | +0.87 to +0.94 | +0.03 to +0.28 |
| Commitment | +0.844 | +0.303 | +0.79 to +0.90 | +0.18 to +0.40 |
| Longest medium section (mi) | -0.506 | +0.248 | -0.64 to -0.25 | -0.10 to +0.49 |
| Longest extreme section (mi) | +0.426 | +0.244 | +0.17 to +0.67 | -0.13 to +0.58 |

PC1 is most strongly associated with Exposure (+0.92), Route finding (+0.91), Rockfall (+0.87). These are interpretations of the observed loadings, not predefined endurance/technical axes.

PC2 is most strongly associated with Recorded distance (+0.93), Recorded gain (+0.88), Medium crux density (-0.50). These are interpretations of the observed loadings, not predefined endurance/technical axes.

The 200 bootstrap fits refit the scaler and PCA, then align component identity/signs. Their percentile ranges describe sensitivity to resampling this small cohort. They assume exchangeable routes and do not correct shared-path dependence; broad ranges should reduce confidence in naming an axis. These are exploratory stability intervals, not population-confidence claims.

## UMAP and t-SNE findings

UMAP defaults: 15 neighbors, minimum distance 0.1, Euclidean metric, seed 42. The sensitivity set uses 5/30 neighbors, minimum distance 0.5, and seed 43. t-SNE defaults: perplexity 10, PCA initialization, automatic learning rate, 1,500 iterations, seed 42; comparisons use perplexities 5/20/30 and an alternative random initialization with seed 43 (changing the seed alone with deterministic PCA initialization is not a meaningful initialization stress test).

For each view, trustworthiness measures unexpected neighbors introduced by the 2D map (closer to 1 is better). Five-neighbor overlap measures how many exact high-dimensional neighbors remain in the plot (closer to 1 is better). Distances tied by identical ratings can make exact-neighbor scores sensitive to tie ordering. No metric validates a real difficulty ordering.

| View | Method | Trustworthiness (k=5) | Mean input-neighbor overlap | Alternate seed/init neighbor agreement |
|---|---|---:|---:|---:|
| numeric_qa_37 | PCA | 0.883 | 57.3% | — |
| numeric_qa_37 | UMAP | 0.876 | 62.7% | 71.9% |
| numeric_qa_37 | t-SNE | 0.898 | 67.6% | 69.2% |
| usable_profiles_96 | PCA | 0.922 | 42.3% | — |
| usable_profiles_96 | UMAP | 0.943 | 59.2% | 71.2% |
| usable_profiles_96 | t-SNE | 0.967 | 67.5% | 78.5% |
| ratings_only_100 | PCA | 0.954 | 70.0% | — |
| ratings_only_100 | UMAP | 0.980 | 69.0% | 74.4% |
| ratings_only_100 | t-SNE | 0.987 | 77.6% | 83.8% |
| observed_segments_100 | PCA | 0.912 | 40.6% | — |
| observed_segments_100 | UMAP | 0.949 | 58.0% | 71.4% |
| observed_segments_100 | t-SNE | 0.953 | 65.2% | 80.0% |

For the broader 96-track cohort, nonlinear sensitivity results are:

| Method | Variation | Trustworthiness | Agreement with default map neighbors |
|---|---|---:|---:|
| UMAP | neighbors 15, min_dist 0.1, seed 43 | 0.942 | 71.2% |
| UMAP | neighbors 5, min_dist 0.1, seed 42 | 0.941 | 65.6% |
| UMAP | neighbors 30, min_dist 0.1, seed 42 | 0.948 | 76.2% |
| UMAP | neighbors 15, min_dist 0.5, seed 42 | 0.945 | 79.8% |
| t-SNE | perplexity 10.0, seed 43, init random | 0.955 | 78.5% |
| t-SNE | perplexity 5.0, seed 42, init pca | 0.943 | 71.2% |
| t-SNE | perplexity 20.0, seed 42, init pca | 0.959 | 77.7% |
| t-SNE | perplexity 30.0, seed 42, init pca | 0.963 | 70.2% |

UMAP and t-SNE preserve local relationships, and neither provides PCA-style feature loading arrows. Apparent islands, their spacing, orientation and area are not calibrated difficulty differences or evidence of natural route clusters. Parameter/seed agreement shows which local neighborhoods are more stable. t-SNE is a visualization here; this implementation does not offer an out-of-sample transform.

## Encoding and feature choices

The eleven-feature model uses recorded distance, smoothed positive gain, medium/extreme crux density, nonlinear Class 1–5 encoding (1/2/4/8/16), and four ordinal source risk labels (0–4). Density remains percent-grade based: medium 20–35%, extreme above 35%. Longest continuous medium and extreme sections are included at user request. Total steep mileage remains outside the main matrix. Standardization gives every feature equal initial variance; correlated steepness measures can therefore receive extra weight. The nine-feature ablation quantifies that choice.

Replacing nonlinear class encoding with linear Class 1–5 changes the broader cohort's first-two-PC variance to 69.2% and retains 90.4% of input-space five-neighbor relationships. The selected encoding is a modeling assumption, not measured spacing between climbing grades.

## Four qualified profiles: observations and uncertainty

All four GPX files exist. The unchanged 100 m edge filter excludes sparse jumps; these profiles fall below the unchanged 95% recorded-length gate. Strict source-track densities remain missing. The additional 100-route map uses densities on accepted segments for every route, without imputation or bridging excluded edges. This does not promote any numeric-QA or complete-itinerary flags.

The following lower/upper ranges allocate excluded recorded chord distance outside or entirely inside each individual grade band. Upper bounds are separate band-wise possibilities, not simultaneous allocations. They cannot bound true terrain distance, unrecorded approaches/descents or smoothing error.

| Route | Accepted recorded distance | Observed medium density | Medium chord bound | Observed extreme density | Extreme chord bound |
|---|---:|---:|---|---:|---|
| Mt. Columbia - West Slopes | 94.7% | 17.6% | 16.6–21.9% | 6.3% | 6.0–11.3% |
| Huron Peak - North Ridge from Lulu Gulch | 91.2% | 23.0% | 20.9–29.8% | 15.5% | 14.1–23.0% |
| Harvard and Columbia Traverse | 90.3% | 24.6% | 22.2–31.9% | 14.3% | 12.9–22.6% |
| Snowmass Mountain - West Slope | 89.9% | 23.4% | 21.0–31.1% | 25.2% | 22.7–32.7% |

Research retained the current route identities. Older Columbia lines need matching against its rerouted trail; opposite-direction traverse reports and mixed Snowmass S-Ridge/West Slope tracks cannot substitute automatically. Candidate evidence and disposition are recorded in the existing project config.
- [co14-035 source](https://www.14ers.com/route.php?route=colu2): Current official West Slopes description is authoritative; older scree-line tracks require reroute matching.
- [co14-086 source](https://www.14ers.com/route.php?route=huro4): Lulu Gulch North Ridge identity retained; participant alternatives need matching start and descent.
- [co14-086 source](https://www.14ers.com/php14ers/tripreport.php?trip=19587): Candidate from linked participant forum; not downloaded or verified.
- [co14-092 source](https://www.14ers.com/route.php?route=harv4): Official Harvard-to-Columbia traverse retained; reverse-direction reports are not identical itineraries.
- [co14-096 source](https://www.14ers.com/route.php?route=snow2): West Slope retained.
- [co14-096 source](https://www.14ers.com/php14ers/tripreport.php?trip=20795): S-Ridge ascent/West Slope descent GPX candidate mixes itineraries; unsuitable as direct West Slope replacement.
- [co14-035 source](https://www.14ers.org/mount-columbia-project-summary/): CFI reconstruction context confirms need to distinguish old alignments; does not verify GPX geometry.

## Requested route comparisons

These are actual recorded profiles, not complete round-trip totals. The common 96-profile model uses all eleven variables for neighbor comparisons.

| Route | Class | Recorded distance (mi) | Recorded gain (ft) | Longest medium (mi) | Longest extreme (mi) |
|---|---:|---:|---:|---:|---:|
| La Plata Peak - Northwest Ridge | 2 | 4.58 | 4393 | 0.081 | 0.037 |
| Quandary Peak - East Ridge | 1 | 3.17 | 3349 | 0.081 | 0.149 |
| Capitol Peak - Northeast Ridge | 4 | 8.24 | 5311 | 0.124 | 0.062 |
| Quandary Peak - West Ridge | 3 | 2.80 | 2682 | 0.056 | 0.031 |
| La Plata Peak - Southwest Ridge | 2 | 3.76 | 3611 | 0.074 | 0.074 |
| La Plata Peak - Ellingwood Ridge | 3 | 5.24 | 5143 | 0.137 | 0.199 |

Closest standardized-input neighbors for the requested routes:
- La Plata Peak - Northwest Ridge: Mt. Yale - Southwest Slopes, Mt. Shavano - East Slopes, Mt. Massive - Southwest Slopes, Huron Peak - Northwest Slopes, Sunshine Peak - Via Redcloud Peak.
- Quandary Peak - East Ridge: Handies Peak - Southwest Slopes, Torreys Peak - South Slopes, Grays and Torreys, Grays Peak - North Slopes, Mt. Sherman - West Slopes.
- Capitol Peak - Northeast Ridge: Mt. Wilson + El Diente Traverse, North Maroon Peak - Northeast Ridge, Snowmass Mountain - East Slopes, Longs Peak - Loft Route, Longs Peak - Keyhole Route.
- Quandary Peak - West Ridge: Windom Peak - West Ridge, Wetterhorn Peak - Southeast Ridge, Mt. Eolus - Northeast Ridge, Castle Peak - Northeast Ridge, Torreys Peak - Kelso Ridge.
- La Plata Peak - Southwest Ridge: Castle and Conundrum, Windom Peak - West Ridge, Castle Peak - Northeast Ridge, Uncompahgre Peak - South Ridge, Blanca and Ellingwood.
- La Plata Peak - Ellingwood Ridge: North Maroon Peak - Northeast Ridge, Pyramid Peak - Northeast Ridge, Mt. Wilson + El Diente Traverse, Kit Carson Peak - East Ridge, Longs Peak - Loft Route.

Adding longest sections retains 67.3% of the original nine-feature input-neighbor relationships. The original nine-feature first-two-PC variance was 78.1%. This ablation exposes correlated-feature weighting; an increase or decrease in variance captured alone does not establish a better model.

Correlations involving the added features:
- Longest medium section (mi): Exposure (-0.46), Class encoding (-0.43), Extreme crux density (-0.41).
- Longest extreme section (mi): Extreme crux density (+0.52), Route finding (+0.36), Rockfall (+0.33).

## Readiness and next decisions

**Phase Four exploratory engineering is complete:** all three methods, parameter/seed checks, PCA bootstrap intervals, local interactive plots and a written comparison are delivered. **Final complete-itinerary PCA/ranking acceptance remains pending:** 0 of 100 routes have verified full dry-itinerary features. Shared approaches and incomplete returns still affect recorded distances and profiles.

Before Phase Five, resolve itinerary scope and the two outstanding metadata cases, review profile sensitivity/gaps, and inspect shared-path evaluation groups. A synthetic ranking baseline can be engineered separately, but these exploratory plots do not establish objective route difficulty or predict safety. Fit scaler/embeddings on training data only for supervised evaluation; the cohort-wide fits here are descriptive.

## Reproduction and sources

```bash
python outputs/block3_embeddings.py
python tests/test_block3.py
```

The module uses the ignored local `work/phase4_runtime` package target when present. Else install the recorded versions into your chosen research environment. Official PyPI wheel downloads and hashes are retained under `work/phase4_wheels`; runtime versions and source/config/code/feature hashes are stored in `analysis.json`. Nothing relies on a remote plotting CDN.

Methods: [scikit-learn PCA](https://scikit-learn.org/stable/modules/generated/sklearn.decomposition.PCA.html), [StandardScaler](https://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.StandardScaler.html), [trustworthiness](https://scikit-learn.org/stable/modules/generated/sklearn.manifold.trustworthiness.html), [UMAP parameters](https://umap-learn.readthedocs.io/en/latest/parameters.html), [UMAP reproducibility](https://umap-learn.readthedocs.io/en/latest/reproducibility.html), [t-SNE parameters and cautions](https://scikit-learn.org/stable/modules/generated/sklearn.manifold.TSNE.html).

## October 4, 2026: website interpretation and biplot delivery

This section supersedes the historical presentation guidance above for the live site. The original research cohorts and ranking outputs remain unchanged. The website audit found 103 plotted profiles and two groups totaling 103, despite a header/footer claiming 100 and manifest 1.2.0. Its “terrain geometry” description omitted class and risk ratings; its “dominant terrain-difficulty gradient” and “spread = real difference” captions overclaimed what PCA establishes. UMAP's forced-zero domain wasted most of the chart. The page explicitly lacked loading data.

### Completed plan and deliverables

1. Audit the live page, identity manifest, saved scaler/components and current CSV. Reconstruct the frozen 103-route PCA to numerical tolerance before deriving anything.
2. Preserve all original PCA/UMAP/t-SNE coordinates, cluster assignments, feature rows, scores and ranks. Ship a separate versioned interpretation bundle, avoiding a silent cohort change.
3. Calculate exact correlation biplot points/arrows, component variance, feature contributions, representation quality, 200 aligned route-bootstrap loading intervals, full-feature neighbors and projection diagnostics. Reuse `block3_embeddings.py` numerical functions.
4. Audit encoding and correlated-feature sensitivity. Use descriptive labels supported by measured correlations and keep nonlinear axes unnamed physically.
5. Publish `site_embeddings.json`, the reproducible `scripts/build_site_embeddings.py`, numerical tests, `site_embeddings_biplot.png`, and `base44_embeddings_prompt.md`. This narrowly scoped public derived visualization bundle contains coordinates and interpretation statistics; raw tracks, full feature tables, source receipts and ranking models remain private.
6. Base44 renders the contract, then verifies counts, arrow scaling, joins, interactions and accessibility. A future separately versioned 108-profile refit should compare cohort and estimate sensitivity before replacing this stable map.

### Population and scope

There are 109 active catalog routes, 108 provisional scores and 103 frozen mapped profiles. IDs co14-103, 104, 106, 109 and 111 have curated ranking inputs but were never part of this embedding fit; their absence from the plots is not a missing ranking. Co14-107 remains identity-unresolved. The bundle lists all six explicitly. Rankings and the 109-row feature CSV are byte-preserved. Feature version stays 3.1.1; the independent embedding interpretation version is `103-interpretation-1.0.0`.

These are **recorded profiles**, often with incomplete approach/return scope, not comparable verified round trips. Four source risk ratings are ordinal, equally spaced numerically for this model; climbing class uses 1/2/4/8/16. These are assumptions, not measured interval scales. All eleven variables are population-standardized. Strongly related inputs receive separate variance weight.

### Evidence-based labels

PC1 captures **45.4%** of variance and is labeled **Exposure & technical terrain**: correlations are exposure +0.914, route finding +0.900, class encoding +0.836, rockfall +0.834 and commitment +0.832. PC2 captures **21.0%**, labeled **Recorded distance & ascent**, with correlations +0.909 and +0.884. The pair captures **66.4%**, leaving **33.6%** outside the display. Neither axis is a fitted or validated difficulty score.

The fixed groups are **Lower exposure · simpler navigation** (59) and **Higher exposure · more complex navigation** (44), relative to this cohort. Existing k-means was fitted in standardized eleven-feature space, not in map coordinates. k=2 had the best tested silhouette (0.292 versus 0.264 at k=3), but this is modest separation and not proof of discrete natural categories. Saved bootstrap agreement near 0.98 is conditional on fixed k and representation, not independent validation or a probability of true membership. We preserve IDs and memberships and improve display labels only.

### Exact biplot contract

Let Z be the centered, population-standardized n×11 matrix, V the saved 11×2 component vectors, T=ZV the saved raw scores, and D the diagonal population SD of those scores. Feature arrows are C=VD, equal to correlations of each input with each component. Route biplot positions are F=TD⁻¹. Consequently **FCᵀ=TVᵀ**, exactly the rank-two standardized reconstruction. There is no decorative arrow multiplier. Raw-score PCA and the unit-SD biplot are different displays and have separate exported coordinates and diagnostics.

Use equal units per screen pixel. A companion correlation circle enlarges the same arrow endpoints for legibility, not their numeric values. Feature representation is C₁²+C₂²; a feature's contribution to an axis is 100V². These quantities are not interchangeable. Route representation is (T₁²+T₂²)/||Zᵢ||², measuring the fraction of that route's squared standardized deviation represented in the plane. It is not source-data quality or certainty.

Longest extreme sections have only **24.3%** representation in these two PCs; medium density **33.5%**, longest medium sections **40.6%**. Short arrows therefore do not mean irrelevant inputs. Their variation often lies outside the plotted plane. Arrow angles approximate feature relationships only when the projection represents those features well. Bootstrap intervals use 200 route resamples with scaler/PCA refitted and component identity/sign aligned (seed 20261004). Shared approaches make observations dependent; these exploratory intervals do not correct that dependence.

### Projection diagnostics and sensitivity

All neighbor diagnostics use k=5 against the original eleven-dimensional standardized space. Trustworthiness penalizes false neighbors introduced by projection. Exact neighbor overlap measures retained members; neither measures predictive accuracy.

| View | Trustworthiness | Exact five-neighbor overlap |
|---|---:|---:|
| Original-score PCA | 0.925 | 41.9% |
| Correlation biplot | 0.922 | 41.6% |
| UMAP | 0.948 | 59.2% |
| t-SNE | 0.963 | 61.9% |

The site should identify similar routes from the exported **full-feature neighbors**, not whichever dots happen to touch. Larger t-SNE fidelity on this cohort does not establish universal superiority. Saved nonlinear parameters remain seed 42, UMAP 15 neighbors/min_dist 0.1, t-SNE perplexity 10/PCA initialization/1,500 iterations; no nonlinear refit occurred in this delivery. Historical seed/parameter studies above belong to their stated research cohorts and should not be presented as new 103-route sensitivity results.

Replacing exponential class coding with linear 1–5 retains **90.9%** of input-space neighbors. Removing the two longest-section inputs retains **68.7%**. Feature definition/weighting materially affects similarity; don't market these neighborhoods as model-independent truth. A family-balanced feature sensitivity and an expanded-cohort comparison are sensible next research steps, not prerequisites to displaying this honest frozen fit.

### Concrete comparisons

- Capitol Northeast Ridge: nearest profiles include Mount Wilson North Slopes from Navajo Basin, Mount Wilson–El Diente Traverse, and North Maroon Northeast Ridge.
- Quandary East Ridge: Handies Southwest Slopes, Torreys South Slopes, and Grays–Torreys combo.
- La Plata Northwest Ridge: Yale Southwest Slopes, Shavano East Slopes, and Massive Southwest Slopes.

These neighbors reflect the eleven recorded attributes; they are not claims of interchangeable hazards, outing lengths or required skills. Route selection should expose QA flags and route identity alongside similarity.

### Reproduce and verify

Run `python3 scripts/build_site_embeddings.py`, then `python3 -m unittest discover -s tests -p 'test_site_embeddings.py'`. The script requires the existing private CSV and audit, refuses mismatched saved PCA reconstruction, and never writes to them. The public contract records their hashes, runtime versions, and full cohort IDs. Unit tests verify exact biplot reconstruction, correlation arrows, coordinate preservation, coverage, bounds and neighbors. The static PNG is a reference preview; Base44 owns interaction and responsive styling according to the supplied prompt.

Primary methods references: [scikit-learn PCA](https://scikit-learn.org/stable/modules/generated/sklearn.decomposition.PCA.html), [trustworthiness](https://scikit-learn.org/stable/modules/generated/sklearn.manifold.trustworthiness.html), and [UMAP FAQ on clustering limitations](https://umap-learn.readthedocs.io/en/latest/faq.html).
