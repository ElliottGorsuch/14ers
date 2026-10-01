# Phase Five: provisional ranking baselines and model card

**Engineering complete; objective route difficulty remains unvalidated.** These models learn an explicit synthetic teacher from real recorded-track features. All source scope/QA flags remain unchanged; human comparison count is zero.

## Plan and delivered files

The six-step plan freezes provenance, records website requirements, defines a weighted teacher, fits linear Bradley–Terry and neural RankNet scorers, evaluates route-group holdouts/ablations, and delivers rankings, sensitivity plots and this model card.

- `private_data/phase5/provisional_rankings.csv`: all 100 route IDs, qualified scores/ranks, strict 96-route ranks, QA and weight-scenario ranges.
- `private_data/phase5/evaluation.json`: splits, teacher/student parameters, scalers, selected epochs, training history, scores, metrics, group-bootstrap intervals and provenance.
- `private_data/phase5/phase5_overview.png`: held-out synthetic metrics and ranking sensitivity.
- `outputs/block4_ranker.py` and `tests/test_block4.py`: reproducible implementation and numerical/leakage checks.

## Synthetic teacher and models

Larger score means harder under this chosen heuristic. Population-standardize features using training routes only for each holdout. Teacher weights: class 0.35, extreme density 0.125, medium density 0.075, mean four risk encodings 0.15, recorded distance 0.10, gain 0.10, longest medium 0.05 and longest extreme 0.05. These are project assumptions, not measured causal contributions. Pair targets are sigmoid(teacher A − teacher B).

Linear Bradley–Terry optimizes pairwise soft cross-entropy with L2=0.02. The neural RankNet uses one shared 8-unit tanh scorer, Adam, dropout=0.1, L2=0.002 and validation early stopping. It is implemented in NumPy with analytic gradients to avoid adding a heavyweight framework; finite-difference tests verify backpropagation. Both models operate on feature differences through a score, not on route IDs, clusters, Elo or teacher scores as predictor columns.

The linear model has the same form as the synthetic teacher. Good imitation is expected and is a pipeline sanity check, not independent scientific validation. Near-tie accuracy excludes teacher probabilities within 0.1 of 0.5; exact student ties receive half credit. MSE compares probabilities to the teacher, not to observed human outcomes. No empirical human calibration, NDCG or objective safety metric is claimed.

## Grouped holdout evaluation

Split groups before generating pairs: 20% test groups, then 20% of remaining groups for validation. Shared-path connected groups cannot cross partitions. Seeds 42/43/44 repeat the experiment, with nine/eleven inputs and strict 96/qualified 100 cohorts. The teacher is fixed to eleven features for each comparison, so nine-feature students lack the longest-section inputs. Validation chooses RankNet stopping; test routes never fit scalers, optimizers or stopping criteria.

| Cohort / inputs | Model | Mean test soft loss | Mean excess over teacher entropy | Mean non-tie accuracy | Mean Spearman vs teacher |
|---|---|---:|---:|---:|---:|
| usable_profiles_96_11 | BT_linear | 0.6559 | 0.0002 | 100.0% | 0.993 |
| usable_profiles_96_11 | RankNet | 0.6563 | 0.0006 | 100.0% | 0.995 |
| usable_profiles_96_11 | constant_tie | 0.6931 | 0.0374 | 50.0% | — |
| usable_profiles_96_9 | BT_linear | 0.6577 | 0.0020 | 100.0% | 0.953 |
| usable_profiles_96_9 | RankNet | 0.6584 | 0.0026 | 100.0% | 0.948 |
| usable_profiles_96_9 | constant_tie | 0.6931 | 0.0374 | 50.0% | — |
| observed_segments_100_11 | BT_linear | 0.6274 | 0.0003 | 100.0% | 0.995 |
| observed_segments_100_11 | RankNet | 0.6290 | 0.0019 | 100.0% | 0.995 |
| observed_segments_100_11 | constant_tie | 0.6931 | 0.0661 | 50.0% | — |
| observed_segments_100_9 | BT_linear | 0.6290 | 0.0019 | 100.0% | 0.941 |
| observed_segments_100_9 | RankNet | 0.6315 | 0.0045 | 100.0% | 0.914 |
| observed_segments_100_9 | constant_tie | 0.6931 | 0.0661 | 50.0% | — |

The regularized linear scorer is the default baseline: it has lower mean held-out soft loss than RankNet in these experiments and is easier to inspect. RankNet remains a tested comparison model; no advantage over the linear teacher is claimed. Future independent human labels may justify a different model.

Constant-tie scores have undefined rank correlation; null is retained rather than claiming zero correlation. Repeated splits overlap and are not independent folds. Bootstrap intervals resample held-out route groups (200 replicates per split), not individual pairs; they describe synthetic-test sensitivity and depend on the provisional overlap grouping.

| Experiment | Seed | Train / validation / test routes | Train / validation / test groups | Held-out pairs | RankNet selected epoch |
|---|---:|---|---|---:|---:|
| usable_profiles_96_11 | 42 | 65 / 14 / 17 | 42 / 11 / 14 | 136 | 196 |
| usable_profiles_96_11 | 43 | 58 / 16 / 22 | 42 / 11 / 14 | 231 | 175 |
| usable_profiles_96_11 | 44 | 58 / 17 / 21 | 42 / 11 / 14 | 210 | 298 |
| usable_profiles_96_9 | 42 | 65 / 14 / 17 | 42 / 11 / 14 | 136 | 195 |
| usable_profiles_96_9 | 43 | 58 / 16 / 22 | 42 / 11 / 14 | 231 | 215 |
| usable_profiles_96_9 | 44 | 58 / 17 / 21 | 42 / 11 / 14 | 210 | 93 |
| observed_segments_100_11 | 42 | 70 / 12 / 18 | 44 / 11 / 14 | 153 | 182 |
| observed_segments_100_11 | 43 | 61 / 18 / 21 | 44 / 11 / 14 | 210 | 177 |
| observed_segments_100_11 | 44 | 65 / 16 / 19 | 44 / 11 / 14 | 171 | 264 |
| observed_segments_100_9 | 42 | 70 / 12 / 18 | 44 / 11 / 14 | 153 | 144 |
| observed_segments_100_9 | 43 | 61 / 18 / 21 | 44 / 11 / 14 | 210 | 230 |
| observed_segments_100_9 | 44 | 65 / 16 / 19 | 44 / 11 / 14 | 171 | 37 |

Exact route IDs, held-out class counts and intervals are in evaluation JSON. Even 4,950 possible pairs among 100 routes are only 100 route observations; pair counts are not an independent sample size.

## Provisional full-roster outputs and sensitivity

Final display models refit on their entire descriptive cohort using median validation-selected epochs from the corresponding eleven-feature experiments. Their in-sample rankings are separate from held-out evaluation. Four routes lack strict densities and therefore have blank strict ranks; accepted-segment observations support the explicitly qualified 100-route view. Neither view has verified full dry itineraries.

Weight scenarios include the original nine-feature heuristic, a technical emphasis and an endurance emphasis. Rank ranges across these scenarios are assumption sensitivity, not uncertainty confidence intervals. RankNet/linear disagreement is likewise not a measured safety uncertainty. Scores from differently fitted cohorts cannot be directly compared.

Illustrative highest synthetic teacher positions in the qualified view (not a recommended objective difficulty ordering):

| Position | Route | Class | Weight-scenario position range |
|---:|---|---:|---|
| 1 | Crestones Traverse | 5 | 1–1 |
| 2 | Crestone Needle - Ellingwood Arete/Ledges | 5 | 2–14 |
| 3 | Bells Traverse | 5 | 3–36 |
| 4 | Little Bear + Blanca Traverse | 5 | 4–25 |
| 5 | Mt. Wilson + El Diente Traverse | 4 | 5–7 |
| 6 | Capitol Peak - Northeast Ridge | 4 | 3–10 |
| 7 | Pyramid Peak - Northeast Ridge | 4 | 6–8 |
| 8 | North Maroon Peak - Northeast Ridge | 4 | 8–9 |
| 9 | Little Bear Peak - West Ridge and Hourglass | 4 | 5–37 |
| 10 | Crestone Needle - South Face | 4 | 8–38 |
| 11 | La Plata Peak - Ellingwood Ridge | 3 | 7–13 |
| 12 | Bierstadt+Sawtooth+Blue Sky | 3 | 6–18 |

## Model card and next-phase readiness

Intended use: local exploratory synthetic baselines, implementation validation, and planning community comparison collection. Not validated for route recommendations, conditions, legal access or a real-world difficulty ranking. Missing itinerary scope, smoothing sensitivity, ordinal encoding assumptions, correlated variables and shared geometry remain limitations. No human votes were fabricated.

Phase Six comparison-schema/collection engineering can begin. Obtain independent route-pair evidence, preserve random evaluation comparisons outside active selection, check graph connectivity, and evaluate human outcomes before claiming calibrated ranking quality. Complete-itinerary coverage and the two metadata cases remain required for final acceptance.

## Website requirement recorded

The final website should retain PCA/UMAP/t-SNE graphs, named exploratory clusters with feature summaries/stability, route hover cards, geographic location/source links, clicked-route similar neighbors and alternate-route comparisons. Geographic location is distinct from embedding position. Cluster definitions must be based on standardized input features and validated for stability, not manually inferred from UMAP islands. This phase records the requirement; it does not deploy a website or assert discovered clusters.

## Reproduction

```bash
python3 outputs/block4_ranker.py
python3 tests/test_block4.py
```

Model/data/config hashes and installed runtime versions are in evaluation JSON. Saved NumPy arrays in JSON support score reconstruction without executable pickle files.

Primary method references: [RankNet paper](https://www.microsoft.com/en-us/research/publication/learning-to-rank-using-gradient-descent/), [GroupShuffleSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GroupShuffleSplit.html), [SciPy L-BFGS-B](https://docs.scipy.org/doc/scipy/reference/optimize.minimize-lbfgsb.html).
