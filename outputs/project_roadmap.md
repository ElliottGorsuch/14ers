# Colorado 14er difficulty project: technical roadmap and ingestion handoff

Updated September 30, 2026. Manifest **1.2.0** contains **100 different official routes**, with 100 acquired, checksum-verified GPX files and 100 distinct timestamp-independent geometry hashes. All 58 mandatory summit targets remain covered (53 ranked standards, five named standards, 42 alternate selections). Stable IDs and original requested names remain historical identifiers; canonical names define the active cohort.

## Phase 1 — frozen roster and contract

The latest user instruction supersedes the earlier allowance for exact duplicates. Kiener's is excluded for snow dependence; the custom Chicago Basin combination is excluded; six exact-source aliases are replaced. Individual Windom, Eolus, Sunlight and North Eolus routes remain because they provide mandatory summit coverage. Their shared Needleton approach is recorded as a connected evaluation group, not counted as four independent approaches.

Princeton remains represented by #18 East Slopes. The extra #90 Southwest Ridge lacked an official route-page match, and its participant GPX descends a basin gully rather than the intended reverse-ascent itinerary. #90 now holds Torreys West Ridge. The old participant files remain private historical evidence and are not imported into the selected dataset.

| Slot | Active route | Official source / trip-report activity |
|---|---|---|
| #68 | Mt. Bierstadt - East Ridge | [Route](https://www.14ers.com/route.php?route=bier3) · [Report](https://www.14ers.com/php14ers/tripreport.php?trip=23510) |
| #69 | Crestone Needle - Ellingwood Arete/Ledges | [Route](https://www.14ers.com/route.php?route=cnee5) · [Report](https://www.14ers.com/php14ers/tripreport.php?trip=15230) |
| #76 | Tabeguache Peak - West Ridge | [Route](https://www.14ers.com/route.php?route=tabe3w) · [Report](https://www.14ers.com/php14ers/tripreport.php?trip=10380) |
| #77 | La Plata Peak - Ellingwood Ridge | [Route](https://www.14ers.com/route.php?route=lapl3) · [Report](https://www.14ers.com/php14ers/tripreport.php?trip=23669) |
| #78 | Grays Peak - South Ridge | [Route](https://www.14ers.com/route.php?route=gray3) · [Report](https://www.14ers.com/php14ers/tripreport.php?trip=20351) |
| #84 | Mt. Blue Sky - West Ridge from Guanella Pass | [Route](https://www.14ers.com/route.php?route=evan3) · [Report](https://www.14ers.com/php14ers/tripreport.php?trip=5221) |
| #89 | Grays Peak - Southwest Ridge | [Route](https://www.14ers.com/route.php?route=gray8) · [Report](https://www.14ers.com/php14ers/tripreport.php?trip=14394) |
| #90 | Torreys Peak - West Ridge | [Route](https://www.14ers.com/route.php?route=torr11) · [Report](https://www.14ers.com/php14ers/tripreport.php?trip=3289) |
| #93 | Kit Carson Peak - East Ridge | [Route](https://www.14ers.com/route.php?route=kitc3) · [Report](https://www.14ers.com/php14ers/tripreport.php?trip=9208) |

The earlier approved replacements remain: #85 Sherman West Slopes, #87 Missouri West Ridge (Rockdale 2WD), #94 Belford Southwest Slopes and #95 Kit Carson North Ridge. #97 remains the Bierstadt–Blue Sky Tour de Abyss. Class 1–5 encoding remains **1/2/4/8/16**; the replacement Ellingwood Arete/Ledges has observed official Class 5, without a user grade override. Its ledges approach and standard South Face descent require exact branch/coverage review.

Selection targets popularity subject to peak coverage. Route-specific trip-report references are recorded for the nine new replacements, with evidence checked September 30, 2026. A report may cover a route as part of a larger outing; that establishes route activity, not the exact selected complete itinerary. Report counts have not been collected consistently, and the cohort is not a measured global top 100. Peak condition/report totals are not used as route popularity counts.

Complete itinerary scope includes approach and descent. Multiple published totals are selected only by explicit start or approach/descent variant. Lower/upper starts, winter closures and snow descents are not mixed. Published starts are labels rather than proof that GPX covers them. Exact source and geometry aliases are prohibited in the final cohort; related approaches and near overlaps require grouped evaluation and Phase 3 spatial review.

## Phase 2 — acquisition and ingestion

Normal browser GPX controls were used after the user's explicit approval of the displayed download agreement. The selected snapshot is **100 downloaded / 0 missing / 0 exact duplicates**. All 100 files independently pass GPX XML, Colorado-coordinate, elevation-coverage and SHA-256 checks. Every point has elevation; this is availability, not an assessment of elevation accuracy. The private archive has 105 original files: 100 selected tracks, three approach components and two retired participant candidates.

Private originals and overview captures are in `private_data/browser_downloads/`; reproducible imported files, sidecars and the frozen snapshot are in `private_data/raw/`. Original bytes are preserved. Download receipts record observed source URL, acquisition time, accepted agreement and file hashes. Raw tracks and permissions are excluded from Git and the deliverable ZIP.

Ingestion **2.1.1** parses prefix and suffix start labels, preserves 2WD/4WD distinctions, and handles published approach/descent variants. Princeton #18 now selects the published lower 2WD start totals. **98 rows have complete parsed metadata.** Remaining metadata review:

- **#41 Culebra:** the overview omits units on its multiple gain values. The ranch-HQ start is selected, but gain remains missing rather than silently assuming units.
- **#58 North Eolus:** published 0.20-mile / 250-foot values are an addition to Mt. Eolus, not a Needleton-to-summit round trip. Both totals are withheld for the selected complete itinerary.

Coverage diagnostics are persisted in the existing status table and sidecars: segment-safe source track distance, ratio to selected published mileage, endpoint separation and review priority. **97 selected source tracks have endpoint separation above 500 m**. This is a diagnostic, not proof that each is ascent-only. The review queue contains 77 start/same-path-return cases, 19 loop/traverse-return cases, three Chicago Basin approach/return cases and one North Eolus connector case. None is automatically certified dry or complete.

Phase 2 collection and snapshot integrity are complete. **Full Phase 2 itinerary acceptance remains pending: 0/100 certified training eligible.** This count reflects conservative verification flags; no acquisition is missing. Browser success is recorded separately from historical Python HTTP 403. Source-owner modeling/publication permission evidence remains undocumented; the download waiver does not establish those rights. No publication action is part of this handoff.

### Reproduce and validate

```bash
python outputs/block1_scraper.py --manifest outputs/research_route_manifest.csv \
  --out private_data/raw --contact local-private-project --offline \
  --download-agreement-accepted --browser-download-dir private_data/browser_downloads
python scripts/audit_phase2.py --data-root private_data/raw
python scripts/sync_deliverables.py
python scripts/validate_project.py
python tests/test_block1.py
```

Import exit 2 means the full reviewed-itinerary gate is unmet; audit exit 0 means snapshot integrity passes. The Colab notebook embeds the canonical manifest and implementation. Local provenance records exact runtime/package versions. Fixtures verify ingestion behavior and tamper detection; they do not certify live route scope.

### Phase 3 entry plan and readiness

1. Start with raw-file diagnostics for all 100 tracks: segment boundaries, gaps, elevation noise, source-distance discrepancies and shared paths. Preserve raw bytes and use versioned derived geometry.
2. Resolve Culebra gain units and North Eolus full-itinerary totals with source evidence.
3. Review each GPX start, summit visits, branch and descent against its selected itinerary. Supply missing approaches/returns from documented components. Reverse only a confirmed same-path out-and-back; do not invent straight-line joins or double ascent gain.
4. Prioritize Chicago Basin's shared approach, summit-only traverses, Ellingwood Arete's ledges branch/South Face descent, La Plata's Northwest Ridge descent and Tour de Abyss's summit-parking start.
5. Record reviewer, date, source/component hashes and assembly decisions before changing `itinerary_verified` or `dry_summer_verified`. Version the manifest and regenerate all handoffs when scope changes.
6. Compute provisional profile metrics with uncertainty, then freeze the feature matrix only after coverage, sampling, noise and overlap review. Modeling remains gated on reviewed features.

**Phase 2 handoff readiness:** all 100 raw routes are available. Phase 3 recorded-track processing is now implemented below; final complete-itinerary features and training are pending the review queue. Use `outputs/phase2_review.json` for machine-readable counts and `private_data/raw/review_required.csv` for per-route work.

## Phase 3 — implemented GPX feature engineering and QA

Block 2 (`outputs/block2_features.py`, feature version **3.1.0**) has processed all **100 acquired tracks**. This phase adds one canonical Python module, its analytical tests, one private feature CSV and one aggregate review JSON. The feature dictionary and parameters live in the existing project config; Block 2 is added to the existing Colab notebook. No duplicate manifest, standalone dictionary or additional notebook is created.

### Thresholds and feature definitions

The latest user request specifies **percent grade**, superseding the old degree thresholds. Absolute percent grade is `100 * abs(elevation_change_m) / horizontal_distance_m`. Thus 20% is approximately 11.31 degrees and 35% approximately 19.29 degrees; 35 degrees would instead be about 70% grade. [USGS slope conversion definition](https://ghsc.code-pages.usgs.gov/lhp/pfdf/guide/utils/slope.html).

| Feature | Definition / units |
|---|---|
| `distance_mi`, `gain_ft` | Verified full-itinerary horizontal distance and positive cleaned elevation change |
| `crux_density_medium` | Percent of valid horizontal distance at 20–35% absolute grade, inclusive |
| `crux_density_extreme` | Percent of valid horizontal distance above 35% grade |
| `crux_medium_mi`, `crux_extreme_mi` | Total horizontal miles within each mutually exclusive band |
| `steep_above20_mi` | Medium plus extreme mileage, at or above 20% grade |
| `longest_medium_mi`, `longest_extreme_mi`, `longest_above20_mi` | Longest continuous horizontal run in the indicated band; resets at gaps and GPX sequence boundaries |
| `yds_encoded` | Class 1/2/3/4/5 → 1/2/4/8/16; retain source raw grade text |
| `exposure_encoded`, `rockfall_encoded`, `route_finding_encoded`, `commitment_encoded` | Low/Moderate/Considerable/High/Extreme → 0/1/2/3/4; original labels retained |

Density is distance weighted, never a fraction of GPX points. The two density bands cannot exceed 100% in total. Total steep mileage measures cumulative demand; the longest run measures sustained demand. Both include uphill and downhill grade; gain sums positive changes only. Risk categories are source judgments, encoded ordinally as a project decision. The allowed labels were checked against the [14ers.com risk definitions](https://www.14ers.com/routes_byriskfactor.php) and the 100 acquired overviews. Unknown/altered labels fail rather than becoming zero.

### Implementation and diagnostics

GPX sequences remain separate. Edges below 0.5 m, above 100 m, missing elevation or exceeding 300% absolute grade split the profile before interpolation and smoothing. These are provisional screening rules, not validated physical limits. Excluded distance is tracked against all recorded within-sequence horizontal distance. Recorded-track densities are withheld when valid-distance coverage is below 95%; accepted steep mileage remains a lower-bound diagnostic. No straight-line inter-segment joins or guessed approaches/returns are generated.

The default profile uses intervals no greater than 10 m and a centered 25 m distance-window elevation mean. Window membership is discretized on the actual equal-distance grid; the effective support may differ slightly from 25 m. Linear endpoint extension preserves a constant slope, but edge behavior and short tracks still warrant review. Raw adjacent-point metrics are retained separately. Every route is also processed with all nine combinations of 5/10/20 m spacing and 0/25/50 m smoothing. A density range above 5 percentage points or gain range above 20% of default gain triggers review. Flat profiles have zero gain and no undefined gain-percentage claim.

The source grade/risk labels and selected published totals are cross-checked against the captured catalog. Original GPX bytes, metadata receipt hashes, snapshot freeze, source-file hashes, implementation/config hashes, parameters and runtime versions provide provenance. The module makes no network calls. The existing reviewed-export adapter is supported: reviewer/date, geometry/conditions evidence, unchanged itinerary fields, boolean review flags and export/file hashes are checked before final feature eligibility. Browser review flags alone cannot release final fields without scope evidence. Distances and gain on recorded tracks are diagnostic and do not replace published full-itinerary values. Recorded/published ratios are reported; they become discrepancy gates only when complete itinerary scope is verified.

Approximate shared paths are screened with 50 m grid cells, sampled at no more than 25 m along accepted edges. At least 50% common occupied cells of the shorter track creates an overlap candidate. Candidate links and prior shared-approach groups form connected evaluation groups. This coarse grid may miss adjacent-cell matches or link incomplete subset tracks; review these groups before evaluation. Exact geometry duplicates remain absent. Acquisition and recording times, speed, identifiers and group membership are excluded as predictors.

### Actual results and readiness

The [aggregate review](phase3_review.json) reports:

- **100 recorded profiles**, with class and all four risk encodings present for all 100 routes.
- **37 profiles pass current numeric QA**, independently of itinerary scope.
- **52 routes** exceed the density sensitivity threshold; **30** have excluded profile edges; **3** exceed the gain sensitivity threshold; **4** have valid-distance coverage below 95%. These flags overlap.
- **2 metadata scope cases** remain: Culebra gain units and North Eolus complete-route totals.
- **46 approximate overlap links** produce **69 connected evaluation groups**, including the predeclared Chicago Basin group.
- **0 complete-itinerary feature rows are eligible** because the 100 complete dry itineraries remain unverified. Final geometry feature columns are empty; `source_track_*` and `raw_track_*` contain clearly scoped diagnostics. Source ratings remain populated.

Engineering and the all-100 provisional computation are complete. Full Phase 3 dataset acceptance remains pending route coverage and flagged profile review. **Phase 4 local exploration is delivered; final complete-itinerary PCA remains pending.** Recorded-track plots label missing approaches/returns and uncertainty. Version 3.1 adds accepted-segment densities for all 100 routes and separate recorded-chord bounds; it preserves the 95% strict-density gate and all eligibility flags.

The private table is `private_data/routes_features.csv`; it is excluded from Git and the ZIP. `outputs/phase3_review.json` carries aggregate readiness, hashes and parameters. The dictionary is `project_config.json → phase3.dictionary`.

```bash
python outputs/block2_features.py
python tests/test_block2.py
python scripts/sync_deliverables.py
python scripts/validate_project.py
```

For another private snapshot, set `--data-root`, `--features` and `--report`; `--project-root` points to the extracted project handoff. Exit 0 means the feature/diagnostic computation succeeded, not that complete-itinerary acceptance passed. Inspect `phase3_dataset_ready` and each row's `feature_eligible`.

Remaining acceptance work: document all starts, branches, summit visits and returns; resolve the two metadata cases; review long gaps/elevation spikes and parameter sensitivity; freeze validated smoothing parameters; review spatial-overlap groups; then rerun the pipeline against the versioned reviewed snapshot. Do not automatically double gain or invent missing return geometry. Profile steepness does not directly measure climbing moves, rock quality or exposure, and resampling cannot recover a crux absent from the original GPX. Select a compact feature set for PCA/model comparisons rather than treating correlated density, mileage and longest-run columns as independent evidence.

## Phase 4 — PCA, UMAP and t-SNE delivered locally

`block3_embeddings.py` version **4.1.0** implements the config's plan: provenance validation, standardized PCA/correlation biplot, seeded UMAP/t-SNE, bootstrap/parameter/encoding/feature-ablation checks, and local report/plots. No new notebook, database copy or external dashboard is introduced. Read the [full Phase Four report](phase4_report.md).

The user-selected primary view has **96 recorded profiles and eleven features**, including longest medium/extreme sections. Its first two PCs explain **68.1%**. The 37-profile numeric-QA view and all-100 ratings comparison expose quality/selection effects; the QA subset includes no Class 5 routes. Adding longest sections preserves **67.3%** of nine-feature input neighbors. Capitol, Quandary East/West Ridge and La Plata Northwest/Southwest/Ellingwood Ridge receive focused comparisons and route buttons.

Four sparse official profiles have only 89.9–94.7% accepted recorded chord distance under the unchanged 100 m exclusion rule. Research finds that some candidate tracks change the selected ascent/descent or traverse direction. Retain all four route identities and strict missing densities. New accepted-segment density fields cover all 100 actual tracks; separate chord-distance lower/upper bounds expose excluded-length uncertainty. A qualified all-100 map uses accepted-segment densities consistently for every route. Bounds do not cover unrecorded itinerary scope or terrain-versus-chord error, and each band's upper allocation is separate.

PCA uses population standardization, consistent correlation arrows, deterministic signs and 200 bootstrap fits. UMAP and t-SNE use recorded seeds and parameter/initialization variations. Apparent islands and global spacing are not a calibrated ranking. Only PCA has loading arrows. Exact-neighbor metrics remain sensitive to ties in the ratings-only view.

Private artifacts are `private_data/phase4/route_exploration.html`, `phase4_overview.png` and `analysis.json`. The HTML is self-contained, with selectors, hover details, highlighted route buttons and input-space neighbors. JSON saves coordinates, learned preprocessing, ablations, parameters and provenance. Static plots are visually inspected, and HTML JavaScript syntax checked. Browser policy blocks local-file interactive preview, so browser interaction is unverified.

**Phase Four exploratory engineering is complete; Phase Five provisional baseline engineering is ready. Final ranking acceptance remains pending full dry-itinerary verification (0/100), two metadata cases, profile sensitivity review and independent comparison evidence.** The roadmap below and `project_config.json → phase5` describe the next implementation. Descriptive cohort-wide transforms must be refitted within training folds for supervised evaluation.

```bash
python3 outputs/block3_embeddings.py
python3 tests/test_block3.py
```

## Phase 5 — provisional baselines delivered

Block 4 (`block4_ranker.py`, version **5.0.0**) implements the six-step plan in `project_config.json → phase5.execution_plan`. The [full report/model card](phase5_report.md) describes teacher assumptions, methods, every experiment and next-phase readiness.

1. Validate feature/config/source hashes and record website graph/cluster/hover/neighbor requirements.
2. Define an eleven-feature synthetic teacher with explicit weights and original-nine/technical/endurance sensitivity scenarios.
3. Fit regularized linear Bradley–Terry and shared eight-unit neural RankNet with sigmoid pairwise soft cross-entropy. NumPy RankNet uses analytic backpropagation, Adam, dropout/L2 and validation stopping; numerical gradient tests validate it without a new framework install.
4. Split shared-path groups before preprocessing or forming pairs. Three seeds compare nine/eleven features and strict-96/qualified-100 cohorts, yielding twelve holdout experiments. Test routes never fit scalers or select epochs.
5. Refit descriptive display models on each full cohort using median selected epochs; export 100 qualified ranks, 96 strict ranks, QA and weight-scenario ranges. Four strict rows remain missing.
6. Deliver plots, model card, reusable JSON parameters, tests and synchronized handoffs.

Teacher weights are class .35, extreme density .125, medium density .075, mean risks .15, recorded distance .10, gain .10, longest medium .05 and longest extreme .05. They are assumptions rather than observed difficulty spacing. The teacher is fixed to eleven features when ablating student inputs. Linear BT has L2=.02; neural RankNet has eight tanh units, dropout=.1, L2=.002, Adam=.01 and validation patience=50/max epochs=600. Larger score means harder under this synthetic heuristic; `P(A harder than B)=sigmoid(score_A-score_B)`.

Actual 96-profile eleven-feature mean held-out excess soft loss: **0.0002 BT**, **0.0006 RankNet**, **0.0374 constant tie**. BT is the default baseline. A linear teacher is representable by the linear scorer; high synthetic imitation is not objective ranking validation. Near-ties are excluded from pair accuracy; exact student ties get half credit. Rank correlation and probability MSE compare against the teacher only. No human calibration or independent safety/difficulty claim is made.

Metrics, exact split IDs/class counts, scalers, coefficients/neural weights, histories and 200-replicate held-out group-bootstrap intervals are saved in `private_data/phase5/evaluation.json`. Bootstrap intervals resample groups, not independent pairs; repeated holdouts overlap. There remain only 100 route observations regardless of pair count. Scenario rank ranges are heuristic-weight sensitivity, not confidence intervals. Full-cohort display ranks are separated from held-out evaluation.

Local deliverables: `private_data/phase5/provisional_rankings.csv` (all 100 IDs), `phase5_overview.png` and `evaluation.json`, plus canonical report/code/tests. No new notebook, duplicate feature CSV, executable pickle or model framework is introduced. All private artifacts stay excluded from the ZIP. All 47 tests pass across Blocks 1–4; the plot is visually reviewed and provenance/bundle checks pass.

**Phase Five provisional engineering is complete. Phase Six comparison-collection engineering can begin.** Final acceptance remains pending independent human comparisons, complete dry-itinerary review (0/100) and two metadata scope cases. Future supervision must preserve route-group holdouts, a random evaluation stream and teacher/Elo separation. Independent evidence could justify nonlinear models or changed weights.

```bash
python3 outputs/block4_ranker.py
python3 tests/test_block4.py
```

## Phase 6 — local comparison backend delivered; live rollout pending

Block 5 (`block5_community.py`, version **6.0.0**) implements the seven-step plan in `project_config.json → phase6`. The [complete Phase Six report](phase6_report.md) contains the flow map, API/entity contract, likelihood/tie choices, sampling/evaluation policy and live-deployment steps. [Aggregate readiness](phase6_review.json) records actual community evidence and provenance.

1. Freeze roster/model contracts; initialize one private append-only SQLite assignment/event store.
2. Issue authenticated server assignments, randomize displayed sides, bind responses to voter/assignment and record exact sampling probabilities.
3. Reserve 990 of 4,950 random pairs for frozen evaluation. Exclude them from training Elo, batch BT and active acquisition; select this lane with 20% probability when available.
4. Record A/B/tie/skip, self-reported completed-both status, conditions, versions, received time and checksum in one transaction with both Elo updates. Identical event retries are idempotent; conflicting retries/duplicate answers are rejected.
5. Replay Elo (K=24, neutral 1500); fit regularized sum-zero BT only on qualified binary training responses. Qualified ties affect Elo only. Skips, non-dry/unknown conditions, inexperienced responses and evaluation events remain excluded.
6. Select training pairs with 20% uniform mixture plus 80% coverage/component-bridge, BT variance, synthetic-model-disagreement, diversity and repeat-penalty acquisition. Store conditional lane × pair × side probabilities. Voter bootstrap and graph connectivity expose evidence limits.
7. Validate ownership, expiry, limits, append-only records, rollback/replay, evaluation isolation and empty-data honesty; deliver API/report/audit and rollout next steps.

**57 tests pass** across Blocks 1–5. WSGI endpoints are tested in-process with fixture sessions; no public server or production identity provider is claimed. Default writes fail closed until a server-validated session callback and private HMAC key are supplied. The event store is distinct from the original route feature CSV and remains excluded from Git/ZIP; fixtures never enter the real store.

Actual evidence: **0 human events**, **100 isolated components**, neutral Elo, null unsupported BT estimates/intervals and no community ranks. No synthetic votes initialize community evidence. Globally comparable ranks need a connected binary graph; the pilot readiness gate additionally requires at least five binary comparisons and two voters per route, which is an engineering threshold rather than proof of quality. Curvature/voter-bootstrap intervals remain exploratory/prior-dependent. Regularization permits numerical fits on disconnected components but does not create cross-component evidence.

**Phase Six local engineering is complete; live comparison rollout remains pending.** Next: canonical code/docs are published to the selected GitHub repository; implement Base44 backend integration and real identity verification; connect the comparison cards; collect real qualified pilot responses; audit concentration/coverage/connectivity; freeze a confirmatory time-separated evaluation snapshot; then proceed to Phase Seven's graphs/clusters/hover/location/neighbor integration. Frozen pair evaluation measures known-route comparisons, not unseen-route generalization, and ongoing metric monitoring is not untouched confirmatory evidence.

```bash
python3 outputs/block5_community.py
python3 tests/test_block5.py
```

## Phase 7 — GitHub/Base44 and elliotgorsuch.com handoff

**Active site catalog / public Route manifest updated October 1, 2026:** the feature table contains 109 IDs (97 retained baseline routes plus 12 requested additions), with 108 rank-ready entries and 103 plot-ready entries, feature version 3.1.1. Only `co14-107` remains rank-pending; six remain plot-pending. This includes unresolved Democrat West Ridge identity; a requested row is not proof of a verified itinerary. Expanded PCA/UMAP/t-SNE and clusters were recomputed together; provisional scores use the saved linear model. Complete-itinerary acceptance and human validation remain pending.

`outputs/route_manifest.csv` (version 2.0.0) is the canonical public Base44 `Route` entity import; `outputs/site_route_manifest.json` carries equivalent records. The previous 100-row CSV is preserved unchanged as `outputs/research_route_manifest.csv`. The frozen project config retains its historical filename/hash and governs only that baseline. The active public roster is generated from the existing feature CSV and site catalog via `python3 scripts/update_site_catalog.py --manifest-only`. Its 109 IDs match the feature table exactly. Upsert by `route_id`; archive retired `co14-008`, `co14-054`, `co14-069`, preserving historical references. Cameron/Lincoln remain only in Decalibron `co14-066`. Link combo itineraries to every summit while retaining one entity per itinerary. Pending cards can be displayed; gate plots/ranks on their readiness flags. Derived feature/model files remain private. The historical 100-route manifest and comparison store remain frozen; migrate the live voting contract separately before enabling expanded-roster votes. The public import does not reset community ratings or votes.

**Curated ranking update, October 1, 2026:** five routes (#103/#104/#106/#109/#111) now have complete eleven-feature vectors and projected provisional scores using the saved Phase Five scaler/linear weights. No global refit occurred; all 103 original score strings remain unchanged, while rank positions were re-sorted over 108 scores. Scope is `qualified_expanded_108_reference_fit`, model `linear_btl`, feature set `eleven_features`. All 109 rows use feature version 3.1.1; the 33-column schema is unchanged. Risk ratings are documented analyst estimates from source reports, not official ordinal ratings. Flags distinguish seasonal Little Bear geometry, Columbia's ascent/start variant/elevation anomaly, Snowmass's partial approach/ascent and Princeton's direct ridge pitch. Cables retains its acquired loop profile. Source links and scope explanations are in README → “Five-route curated ranking update”; private audit contains source hashes, segment cuts and protected scores. Democrat West Ridge (#107) remains identity-pending and unranked. Full dry-itinerary acceptance and human validation remain pending.

**Base44 next step:** stage the public 109-route manifest and private 109-row feature CSV together. Validate exact ID equality, unique IDs, 108 rank-ready records, one null ranking (Democrat), and 103 plot-ready records. Existing embeddings/clusters were not recomputed for these five predictions; leave their plot fields blank and gate plots separately from ranks. Preserve community history and migrate its roster explicitly. Upsert Route by `route_id`; importing public code/docs does not update the live Base44 database. The private CSV and model/GPX files remain local. Use `--rank-curated` for reproducible backfill or `--manifest-only` for public projection; a full rebuild is blocked while the curated 3.1.1 export exists.

**Licensed photo handoff, October 2, 2026:** `assets/photo_manifest.json` contains 61 reusable JPEG assets, 60 summit associations and all 109 route-card mappings. `assets/PHOTO_CREDITS.md` provides per-image authors, source links, licenses and preview changes. Eight cards have terrain-detail/viewpoint photos; most share peak overviews. North Eolus / auxiliary South Little Bear use labeled massif context; winter Little Bear imagery is identified. Import photos separately by route ID, show linked credits/license, and preserve CC BY-SA image adaptation terms. These assets do not change ranking readiness or resolve Democrat's identity. Feature/model outputs remain private and untouched.

**Historical roommate-list reconciliation (before expansion):** the following 12 requests were absent from the 97-route export. They now have IDs `co14-101` through `co14-112`; the table below records the initial source-review notes, not current completeness. Current scope and identity decisions are in `outputs/site_route_additions.json` and the public site manifest.

| Requested route | Verified identity / remaining work |
| --- | --- |
| Huron Southwest Ridge | Official [Southwest Slopes](https://www.14ers.com/route.php?route=huro2) is the likely intended route; retain its source name, not an invented ridge alias. |
| Little Bear West Ridge Indirect | [Official distinct itinerary](https://www.14ers.com/route.php?route=litt8); not the Hourglass route already present as #44. |
| Little Bear Southwest Ridge | [Summer trip report](https://www.14ers.com/php14ers/tripreport.php?trip=19951) documents a dry July ascent and reverse-ridge descent; do not borrow its separate snowy Hourglass-loop metrics. |
| Longs North Face / Cables | [Summer report](https://www.14ers.com/php14ers/tripreport.php?trip=20661) supports identity; establish descent and exact matching track before adding. Keep Class 5 when source-supported. Kiener's remains excluded. |
| Belford–Oxford–Missouri combination | [Official combined route](https://www.14ers.com/route.php?route=miss4), 15 miles / 7,600 ft; one itinerary linked to all three peaks, not three duplicated tracks. #26 covers Belford–Oxford only. |
| Columbia East Ridge | [Frenchman Creek report](https://www.14ers.com/php14ers/tripreport.php?trip=14029) distinguishes it from existing #91 Southeast Ridge; report is a Harvard–Columbia loop, so its total geometry/metrics cannot stand in for a standalone Columbia itinerary. |
| Democrat West Ridge, claimed Class 4 | Identity and grade unresolved. [Buckskin–Democrat report](https://www.14ers.com/php14ers/tripreport.php?trip=20531) describes mostly Class 2/3 and optional harder lines; do not substitute it or impose Class 4 without matching evidence. |
| Lindsey Northwest Ridge | [Official route](https://www.14ers.com/route.php?route=lind2), Class 3 with optional direct Class 4 moves; #42 is Northwest Gully. |
| Princeton Southwest Ridge via Grouse Canyon | [Summer trip report](https://www.14ers.com/php14ers/tripreport.php?trip=3363) verifies the named route; matching complete GPX and metadata remain to collect. #18 is East Slopes. |
| Mount Wilson North Slopes from Navajo Lake trailhead | [Official Class 4 route](https://www.14ers.com/route.php?route=mwil2); select complete trailhead approach rather than the shorter lake-only component. #16 is Southwest Slopes. |
| Snowmass S Ridge | [Summer report with S Ridge ascent and descent](https://www.14ers.com/php14ers/tripreport.php?trip=23538) supports a distinct itinerary; #96 is West Slope. Matching full GPX remains to collect. |
| Sunshine Northwest Face | [Official route](https://www.14ers.com/route.php?route=suns3); distinct from #53 via Redcloud. Sunshine East Ridge remains deferred under the user's summer-route preference. |

Already present: Grays–Torreys #65; Handies Southwest #40 and East #75; Humboldt West #37; Kit Carson North #95; La Plata Ellingwood Ridge #77; Little Bear–Blanca #80; Longs Loft #67; Bells Traverse #82; Missouri West #87; Sawtooth/Bierstadt–Blue Sky #63; Tour de Abyss #97; Blue Sky from Guanella #84; Decalibron #66; Elbert Black Cloud/Southeast #60; Harvard–Columbia #92; Massive Southwest #64; Holy Cross Halo #74; Sherman Iowa Gulch/West Slopes #85; Sneffels Southwest #70; Wilson–El Diente #81; Yale East #71; Pikes Crags/Northwest #73 and Barr/East #30; Quandary West #61; San Luis South #99; Snowmass West #96; Tabeguache Jennings Creek/West #76; Torreys Kelso #62; Wilson Peak Southwest #48. Existing standard routes requested to remain also stay active.

Presentation associations requested for future site catalog: primary Torreys for #65, North Maroon for #82, and Blue Sky for #63/#97; retain all involved summit associations and one stable itinerary ID each. These preferences are recorded here; the 33-column CSV has no primary-peak field, and historical summit_order is not a presentation-category field. Grays–Torreys belongs to Grays/Torreys, not Quandary. Cameron/Lincoln remain associated only with #66, superseding the older spoken keep instructions.

Scope corrections: “Little Browns Creek on Uncompahgre” is unresolved; [the documented Little Browns route](https://www.14ers.com/route.php?route=ante2) is Antero #100. Do not assign that track to Uncompahgre. Tabeguache via Shavano #25 is present with published full-route 12.0 miles / 5,600 ft, but recorded GPX length is only 0.9061 mile / 300.99 ft: this is a connector profile and must be replaced or assembled from verified compatible components before any claim of full-itinerary difficulty. Do not change the published total to the spoken estimate of 11 miles. Pikes Barr #30 has source RT 24.0 miles and recorded track 11.7454 miles; Wilson Peak #48 has source RT 16.0 miles and recorded track 4.7116 miles. Neither discrepancy alone proves missing ascent geometry, but both require endpoint/approach/return review. Existing source-track measurements and reference-model outputs remain unchanged until verified new geometry supports a versioned recomputation. This reconciliation adds no new feature CSV rows.


**User choices confirmed October 1, 2026:** use the existing public [ElliottGorsuch/14ers repository](https://github.com/ElliottGorsuch/14ers) for code/documentation only and use Base44. Chrome authentication is verified; CLI network transport remains unavailable and no local Git remote is configured. All 26 canonical sources, config, roster, aggregate audits, tests and documentation are committed through the browser; all private source tracks, derived per-route data/models, votes and credentials remain local. Base44 uses Deno backend functions, so the tested Python comparison core requires a native adapter/port or separately hosted bridge. Preserve assignment ownership, append-only records, atomic/idempotent Elo and evaluation isolation in that integration; validate live datastore concurrency rather than assuming SQLite semantics transfer. [Official Base44 backend/client guide](https://docs.base44.com/sdk-getting-started/client).


**Final website requirement recorded October 1, 2026:** retain interactive PCA/UMAP/t-SNE graphs with defined, named exploratory clusters; route hover cards identifying the itinerary, climbing class, feature values, source and geographic location; clicked-route nearest neighbors with an explanation of shared features; and alternate-route comparisons. Provide keyboard/touch equivalents. Link plot selections to route detail and provisional rankings.

Define clusters using standardized input features and record method, parameters, cluster summaries and resampling/parameter stability before choosing names or drawing boundaries. Similarity clusters are not difficulty grades or guaranteed natural categories. Embedding axes are not geographic map coordinates; show location separately. No website deployment or cluster assignment is performed in Phase Five.


Keep training and scraping in Python/Colab. Ship compact JSON to the dashboard for the 100 routes: features, coordinates, vectors, baseline scores, source links, model/version metadata, and rating summaries. A `.pkl` or PyTorch file is not automatically executable in a Base44 frontend. Begin with precomputed scores; serve Python inference separately only if interactive retraining/inference becomes necessary. Keep voting and Elo/BT refresh services independent of static plot assets.

Suggested repository layout (adapt to the app's existing scaffold):

```text
project/
  notebooks/01_ingestion.ipynb
  python/ingestion/  python/features/  python/models/
  config/route_manifest.csv  config/feature_schema.json
  tests/
  artifacts/model_card.md  artifacts/model_metadata.json
  app/                         # actual Base44 application scaffold
    src/                       # dashboard components
    public/data/               # only permitted derived JSON/CSV
  private_data/                # gitignored cache, GPX, research exports
  .gitignore
  requirements.lock.txt
```

The frontend should compare endurance, technical difficulty, and uncertainty; show synthetic and community rankings distinctly; and provide links back to source routes. It should not suggest a single ranking guarantees safe conditions or legal access.

Connect the app to GitHub through Base44's supported integration, verify two-way sync with a small reviewed change, and promote only tested data/model versions. Base44 documents two-way sync; this is a frontend/application workflow, not an automatic Python model hosting service. [Base44 GitHub integration](https://base44.com/blog/base44-github-integration), [Base44 backend CLI](https://github.com/base44/cli).

Before changing DNS for the exact requested domain `elliotgorsuch.com`, confirm ownership and whether an existing site must be preserved. Use the actual app dashboard's custom-domain instructions and verify HTTPS after deployment. GitHub browser access and the selected repository are verified; the dashboard and custom domain are not deployed.

Acceptance: versioned approved data loads correctly, vote outcomes replay deterministically, updates are idempotent, no research credentials/source files leak, plots/rankings display uncertainty correctly, GitHub sync is verified, and the chosen domain serves the approved app.

## Running Block 1

1. Open `01_ingestion_colab.ipynb` in Google Colab. Run installation and optionally mount Drive for persistence.
2. Run the embedded code/manifest cell. It preserves an existing manifest so reruns do not erase your reviewed mappings.
3. Review the source terms and download agreement. After obtaining permission for your intended use, set the two execution confirmations to `True`, enter your research contact, and optionally specify a private authorized cookie file.
4. Run ingestion. Inspect `run_summary.json`, `route_status.csv`, and `review_required.csv`. Update source mappings/itineraries and rerun without `refresh` to reuse cached responses. Set `dry_summer_verified` only after reviewing that route's scope.
5. Archive a reproducible private data snapshot and freeze dependency versions from the successful Colab runtime before proceeding to feature engineering.

Standalone equivalent:

```bash
python -m pip install requests beautifulsoup4 pandas defusedxml
python block1_scraper.py --manifest research_route_manifest.csv --out private_data/raw \
  --contact YOUR_RESEARCH_CONTACT \
  --source-permission-confirmed --download-agreement-accepted
```

The CLI exits with code 2 when the complete 100-route eligibility gate is not met, while still saving all available reports and downloads.

## Verification and current limits

The Phase 2 suite contains **19 local tests**, including receipt-hash rejection and preservation of unreviewed scope during browser import, named start ambiguity, effective grade provenance, offline approved-export validation, selected-only HTTP collection and snapshot tampering. The mapped official overview captures and 96 actual GPX files provide live browser evidence, while fixtures remain synthetic. The private all-100 snapshot independently verifies 97 imported GPX files and correctly leaves `phase3_dataset_ready=false`.

Direct public HTTP requests from the prior kickoff development environment returned HTTP 403 for robots, the route index, Elbert's list, and Elbert's detail page. Live GPX downloads and raw HTML selectors therefore remain unverified. The documented page structures and scope corrections were checked through web research; this does not certify the Python scraper against live HTML.

Local fixture tests cover the exact 100-entry manifest, overview metadata, literal JS download links, snow-only/class-5 handling, exact-versus-ambiguous matching, GPX validation, timestamp-independent geometry hashing, cache resume, rate-limit retries, forbidden/external redirects, robots denial, all-100-row blocked reporting, and duplicate detection through an end-to-end fixture run. Fixtures model documented content; they are not captured raw source HTML. The current Phase 1 suite passed **11 tests**, including approved replacements, source/config/notebook/archive agreement, detection of unreviewed manifest changes, and transitive evaluation grouping. The contract audit in `phase1_review.json` has no errors. The notebook validates structurally, executes locally with network execution disabled, and exports all 100 status rows. Synchronization was verified to be idempotent. It has not been executed in a live Colab session.

After authorized access is available, first test one ordinary route, one technical route, and one combination. Save actual HTML fixtures and inspect downloaded tracks before crawling the rest. If Colab is also blocked, use an owner-approved export/API or another source with suitable permission rather than attempting to evade the block.

## October 4 embedding presentation extension

Completed: live-page audit; frozen 103-fit reconstruction; exact correlation biplot; measured axis/feature/group labels; full-feature neighbors; projection fidelity and class/longest-section sensitivity; source/runtime provenance; public visualization contract and preview; numerical tests; Base44 rendering instructions. See the latest section of `phase4_report.md` and `base44_embeddings_prompt.md` for the full ordered plan and results.

Next: Base44 imports `site_embeddings.json` atomically, corrects 109/108/103 counts, implements four views and accessible selection/labels, then verifies all frontend acceptance checks. The six unmapped routes stay visible as pending; co14-107 still needs identity resolution. Follow-on research: separately version a 108-route embedding refit, compare with the 103 reference, assess curated-input and feature-family weighting sensitivity, and evaluate shared-path dependence. Do not silently change the current embedding cohort or any provisional rankings during this presentation rollout. The user-authorized public math delivery is limited to the visualization bundle; private raw records and full feature/model outputs remain excluded.
