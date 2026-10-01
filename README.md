# Colorado 14er route difficulty

A versioned cohort of **100 distinct official Colorado 14er routes**, preserving all 58 mandatory summit targets and the 53/5/42 selection groups. Original requested names and selection IDs are historical; canonical names identify the active routes. Class 1–5 encoding is 1/2/4/8/16.

## Current state — October 1, 2026

Manifest **1.2.0** replaces Kiener's, the custom Chicago Basin combination, the problematic Princeton Southwest Ridge extra and six exact-source aliases. Princeton East Slopes remains #18. The four individual Chicago Basin summits remain and share an evaluation group for their approach. The nine replacements have official sources and supporting trip-report references in the [manifest](outputs/route_manifest.csv).

**100/100 GPX files are acquired and independently verified**, with 100 distinct source routes and geometry hashes, no exact duplicates, and elevations at every track point. Private originals/receipts are in `private_data/browser_downloads/`; the current imported snapshot is in `private_data/raw/`. The archive also preserves three approach files and two retired participant candidates, for 105 originals.

**98/100 rows have complete parsed metadata.** Culebra gain units and North Eolus's complete-itinerary totals still need source review. The importer now distinguishes prefix/suffix start labels and 2WD/4WD starts; Princeton uses its published lower-start totals. Trip-report activity is the popularity indicator; uniform route counts and a measured top-100 ranking have not been established.

**Phase 3 recorded-track features are implemented for all 100 routes; complete-itinerary features remain pending.** Most source files omit some selected approach/return scope: 97 have endpoint separation above 500 m. The existing review table now records coverage priorities, endpoint gaps and source-distance ratios. No track is automatically marked dry or complete; 0/100 are certified training eligible. Review start, branch, summit order and descent, and document assembly before final features or modeling.

The download agreement was accepted under explicit user authorization. Separate source-owner modeling/publication permission remains undocumented. Raw files stay private and excluded from the ZIP. See the [full roadmap](outputs/project_roadmap.md), [project contract](outputs/project_config.json) and [readiness audit](outputs/phase2_review.json).

## Phase 3 results

The feature pipeline uses **percent grade**, with medium = 20–35% and extreme >35%. It calculates distance-weighted crux density, cumulative steep mileage and the longest continuous steep section. All 100 rows include nonlinear class plus ordinal exposure, rockfall, route finding and commitment, with the original 14ers.com labels preserved.

The single private table, `private_data/routes_features.csv`, contains raw and smoothed recorded-track measurements, coverage/gap flags, source-distance ratios, all-route smoothing sensitivity and evaluation groups. Final complete-itinerary geometry fields remain empty until scope and QA pass. The [Phase 3 review](outputs/phase3_review.json) reports 37 numeric-QA passes, 52 density sensitivity cases, 30 tracks with excluded edges, and 69 evaluation groups. Flags overlap; 0 rows currently pass complete-itinerary eligibility.

```bash
python outputs/block2_features.py
python tests/test_block2.py
```

Default parameters and the feature dictionary live in `outputs/project_config.json → phase3`. The existing Colab notebook now includes Block 2, requiring the extracted handoff and a matching private ingestion snapshot. Phase 4 local exploration is complete; final full-itinerary PCA remains gated on route coverage and numeric QA. No raw GPX or derived per-route feature CSV is placed in the ZIP.

## Phase 3 final handoff

[View the Phase Three summary graphic](private_data/phase3_overview.png).

The [Phase 3 roadmap/read-up](outputs/project_roadmap.md#phase-3--implemented-gpx-feature-engineering-and-qa) and [machine-readable review](outputs/phase3_review.json) accompany the [100-route feature table](private_data/routes_features.csv). Recorded profiles and all five class/risk encodings are computed for all 100 selections. Medium crux density covers 20–35% grade; extreme covers >35%. Steep mileage and longest continuous steep runs are also included, with raw values, smoothing sensitivity and quality flags.

**Engineering complete; final dataset acceptance pending.** Numeric profile QA passes 37 routes; 96 have both crux densities available. All 100 still require complete dry-itinerary verification, and final complete-itinerary geometry fields remain blank. The QA flags overlap: 52 density sensitivity, 30 excluded edges, 3 gain sensitivity, 4 insufficient profile coverage and 2 metadata scope cases. Culebra gain units and North Eolus full-route totals remain unresolved. There are 69 approximate evaluation groups to account for shared geometry.

## Phase 4 delivered

Open [the local interactive PCA/UMAP/t-SNE exploration](private_data/phase4/route_exploration.html), [the plot comparison](private_data/phase4/phase4_overview.png), and [the full read-up](outputs/phase4_report.md). The primary 96-profile view now uses **eleven features**, adding longest continuous medium and extreme sections. First-two-PC variance is **68.1%**; adding those variables retains **67.3%** of the original nine-feature input-neighbor relationships. The read-up and route buttons highlight Capitol, Quandary East/West Ridge, and La Plata Northwest/Southwest/Ellingwood Ridge.

The four previously missing profiles—Columbia West Slopes, Huron from Lulu Gulch, Harvard–Columbia Traverse, Snowmass West Slope—have actual GPX, with 89.9–94.7% accepted recorded chord distance. The unchanged quality filter keeps strict densities missing. Feature version **3.1.0** adds **accepted-segment densities for all 100 routes** and separate lower/upper recorded-chord bounds. No missing segment is imputed or bridged. A fourth, qualified 100-track view explores those observations; 37-track numeric-QA and 100-route ratings-only views remain available. Candidate source research and rejected itinerary mismatches are recorded in the existing config/report.

The single existing feature CSV is the database's authoritative table; no duplicate CSV or SQLite copy is introduced. All 100 selections are present with real measurements, explicit scope, missingness and uncertainty. **Complete dry-itinerary feature acceptance remains 0/100**; the two metadata cases and profile sensitivity remain review work.

Phase 5 can begin **provisional baseline engineering** using the explicit cohort/feature whitelist and plan in `project_config.json → phase5`. Split shared-path groups before generating pairs or fitting scalers. Compare nine/eleven features and strict/qualified cohorts; synthetic-label metrics measure imitation of a chosen teacher. Final route-difficulty validation needs reviewed full itineraries and independent comparison evidence.

```bash
python3 outputs/block3_embeddings.py
python3 tests/test_block3.py
```

Phase 4 stays local and uses the isolated ignored runtime with versions recorded in config/analysis JSON. The offline HTML includes Plotly, cohort/color controls, route detail/neighbor buttons and PCA loadings. Browser policy blocks a local-file interactive preview; its JavaScript is syntax checked, with static plots visually reviewed. **57 tests** cover ingestion, features and exploration. README, roadmap, config, existing notebook and ZIP are synchronized.

## Phase 5 delivered — provisional ranking baselines

Read [the full plan, evaluation and model card](outputs/phase5_report.md), inspect [the 100-route provisional rankings](private_data/phase5/provisional_rankings.csv), or open [the result graphic](private_data/phase5/phase5_overview.png). One private `evaluation.json` saves models, scalers, splits, training history, metrics and provenance; no pickle or separate model copies are needed.

Block 4 implements regularized linear Bradley–Terry and a shared eight-unit neural RankNet using NumPy/Adam, dropout and validation early stopping. Tests verify analytic gradients, deterministic training, shared-group separation and score reconstruction. Three group-split seeds compare nine/eleven features and strict-96/qualified-100 cohorts: **12 held-out experiments**. Training routes fit all preprocessing; held-out routes do not enter pair training or stopping decisions.

The synthetic teacher uses explicit weights, including both longest-section variables. Alternative nine-feature, technical and endurance scenarios expose assumptions. In the 96-profile eleven-feature experiments, mean excess soft loss is **0.0002 linear BT**, **0.0006 RankNet**, versus **0.0374 always-tie**. Linear BT is the default baseline; it shares the teacher's linear form, so close imitation is expected. These results do not validate human route difficulty. All rankings carry synthetic/recorded-segment scope; four strict ranks remain missing and human vote counts remain zero.

**Phase 6 comparison-collection engineering is ready.** Final ranking acceptance still requires independent comparisons, complete-itinerary review and the two metadata cases. Route-group bootstrap intervals describe synthetic-test sensitivity; weight-scenario rank ranges are not confidence intervals.

The final website requirement is recorded in `project_config.json → website_requirements` and roadmap Phase 7: PCA/UMAP/t-SNE, named feature-based clusters with stability checks, route hover/location cards, clicked-route similar neighbors and linked alternate comparisons. The local site export now provides exploratory cluster labels; graph integration and deployment are future work; visual islands do not establish natural difficulty categories.

```bash
python3 outputs/block4_ranker.py
python3 tests/test_block4.py
```

## Phase 6 local core delivered; live voting pending

Read [the complete Phase Six map, API contract and next steps](outputs/phase6_report.md) or [the aggregate readiness audit](outputs/phase6_review.json). Block 5 adds one private transactional SQLite event store at `private_data/phase6/community.sqlite` and a derived `community_snapshot.json`. This stores comparisons, not a second GPX/feature database.

Implemented: server assignments/randomized sides, HMAC voter pseudonyms, fail-closed authenticated WSGI writes, ownership/expiry/idempotency/limit checks, append-only events, transactional Elo, deterministic replay, regularized sum-zero batch BT, component checks, voter bootstrap and coverage/disagreement sampling. A frozen **990-pair random evaluation pool** cannot affect training Elo/BT or active acquisition. Exact selection probabilities and self-reported completion/conditions are recorded. Ties update qualified Elo only; skips and evaluation/non-dry/inexperienced responses do not train the dry-summer ratings.

**Actual community evidence is empty:** 0 events, 100 isolated routes, neutral Elo 1500, no global ranks or fabricated confidence intervals. Synthetic rankings remain separate. In-process WSGI tests validate API behavior; a public voting service, production session provider and website are not deployed. All **57 tests** across Blocks 1–5 pass, including transactional rollback, duplicate retries, evaluation isolation and connectivity.

GitHub browser access is verified, and all 26 canonical code/config/roster/audit/documentation/test files have been committed through the browser. The user selected the existing public [ElliottGorsuch/14ers repository](https://github.com/ElliottGorsuch/14ers) for canonical code and documentation only, and selected Base44. Private GPX, cookies, derived per-route features/models and community records remain local; generated ZIP/extracted handoff copies are Git-ignored. CLI network access remains unavailable and no local Git remote is configured. Next: adapt the tested Python contracts to Base44 Deno/session/data semantics or a hosted Python bridge; inject verified sessions and a private HMAC key; connect the comparison UI; pilot real dry-summer completed-both votes; audit connectivity and preserve frozen evaluation before Phase Seven deployment.

```bash
python3 outputs/block5_community.py
python3 tests/test_block5.py
```

The CLI initializes/audits the real store without opening a port or simulating human votes. Test responses exist only in temporary fixture databases. API endpoints and the deployed-host checklist are in the report; the full implementation plan is in `project_config.json → phase6`.

## Site import export

The feature table now contains **109 unique route IDs**, with 103 ready for plots and provisional ranks. Six entries (`co14-103`, `co14-104`, `co14-106`, `co14-107`, `co14-109`, `co14-111`) remain pending; unavailable values stay blank. The local `site_export/` folder holds the private 33-column feature CSV, expanded plot/cluster summaries, route catalog and provenance. Expanded coordinates were refitted together; do not mix them with older exports. Provisional scores project the saved Phase Five linear model; they are not human-validated community ratings.

The public **[site_route_manifest.json](outputs/site_route_manifest.json)** is the Base44 `Route` entity import: a JSON array with exactly the same 109 IDs as the feature CSV. It supplies canonical names, primary peak, all summit associations, published class (null when unavailable), source links and explicit readiness/scope fields. It excludes GPX, recorded coordinates, model outputs, similarity distances, cookies and download receipts. The original `outputs/route_manifest.csv` remains the frozen 100-route research baseline.

Upsert the public manifest into Base44 `Route` by unique `route_id`, then join the private feature import on that key. Import IDs as strings; never assume they are contiguous. Archive existing `co14-008`, `co14-054` and `co14-069` entity records; retain historical references and never reuse those IDs. Cameron and Lincoln occur only within Decalibron `co14-066`. Use `primary_peak` for the main card and `summits` for filters; one combo itinerary stays one entity. Show pending route cards, but only plot/rank records whose readiness flags are true. All `voting_ready` values remain false until the expanded voting-service roster is explicitly migrated. Preserve existing vote history and community ratings on upsert.

Regenerate just this public identity manifest from the existing exports, without recomputing models:

```bash
python3 scripts/update_site_catalog.py --manifest-only
python3 -m unittest discover -s tests -p 'test_site_manifest.py'
```

Running the exporter without `--manifest-only` rebuilds the expanded private catalog from acquired sources and saved baseline inputs. Both paths refresh the public manifest. The catalog includes requested summer itineraries; it does not claim to contain every possible 14er route. Tabeguache's site profile includes separate Shavano ascent and connector segments; the full return remains unverified. The site import is ready for building route cards and exploratory plots, with pending data shown honestly. Applying the manifest to a live Base44 entity remains an import step.

## Canonical files

- `outputs/route_manifest.csv`: frozen version 1.2.0 roster; original requested names are immutable.
- `outputs/project_config.json`: schema, frozen hash, conditions/itinerary policies and evidence state.
- `outputs/block1_scraper.py`: self-contained ingestion implementation.
- `outputs/block2_features.py`: Phase 3 feature computation, all-route sensitivity and overlap QA.
- `outputs/block3_embeddings.py`: PCA, UMAP, t-SNE, stability/feature-ablation checks and local plots.
- `outputs/phase4_report.md`: full findings, four-route research, requested route comparisons and Phase 5 readiness.
- `tests/test_block3.py`: numerical contracts, reproducibility and offline-page checks.
- `outputs/block4_ranker.py`: synthetic teacher, linear BT/RankNet, grouped evaluation and ranking exports.
- `outputs/phase5_report.md`: full Phase 5 plan, findings and model card.
- `tests/test_block4.py`: gradient, leakage, reproducibility and saved-model checks.
- `outputs/block5_community.py`: comparison store, authenticated API boundary, Elo/BT and sampler.
- `outputs/phase6_report.md`: full flow map, API/entity contract and live deployment steps.
- `outputs/phase6_review.json`: actual community readiness and provenance.
- `tests/test_block5.py`: ownership/retries, rollback, replay, evaluation isolation and rating fixtures.
- `outputs/phase3_review.json`: aggregate feature readiness and provenance.
- `tests/test_block2.py`: analytical gradient/units/gap tests and optional private-snapshot checks.
- `outputs/01_ingestion_colab.ipynb`: synchronized Colab handoff with live, offline/export and smoke-test controls, plus Phase 3 feature cells.
- `outputs/project_roadmap.md`: all seven phases, acceptance gates and Phase 6 handoff.
- `scripts/sync_deliverables.py`: refreshes the existing notebook and ZIP.
- `scripts/validate_project.py`: checks the frozen roster and embedded/archive agreement.
- `scripts/audit_phase2.py`: audits a private snapshot and writes an aggregate readiness report.
- `tests/test_block1.py`: local fixtures; they contain synthetic data, not live HTML/GPX evidence.

Inspect existing files before adding artifacts. Edit the canonical files, then synchronize. A deliberate roster/scope change requires a manifest version increment and reviewed hash update. Do not create alternate numbered CSVs/notebooks. Private GPX, export permissions, caches and cookies belong under `private_data/`, which is ignored by Git and excluded from the bundle. Published reports contain aggregate counts, not private source files.

## Local validation

Install the runtime dependencies in your chosen Python environment:

```bash
python -m pip install requests beautifulsoup4 pandas defusedxml numpy
python scripts/sync_deliverables.py
python scripts/validate_project.py
python tests/test_block1.py
```

Python 3.10+ is the target; local fixture verification also passed on the available Python 3.9 runtime. Each ingestion run records its exact Python/package versions in private `run_provenance.json`. A successful Colab environment has not yet been frozen.

## Live source collection

Normal browser downloads have already been accepted and collected for the mapped routes. The following direct-HTTP path remains conditional on its documented usage permission and transport smoke test. Record its evidence in `project_config.json` before using that path. Supply only your own authorized cookie file if needed. First smoke-test ordinary, technical and combined routes:

```bash
python outputs/block1_scraper.py --manifest outputs/route_manifest.csv \
  --out private_data/smoke --contact YOUR_RESEARCH_CONTACT \
  --source-permission-confirmed --download-agreement-accepted \
  --only-routes co14-001 co14-095 co14-097
```

The smoke test requests only selected mapped route pages and their observed GPX controls, plus robots. It reports all 100 IDs; the other 97 are `not_selected`. It exits 2 because a three-route test cannot satisfy the 100-route gate. Inspect actual HTML/GPX and complete itinerary coverage before running the same command without `--only-routes` against `private_data/raw`. Stop on robots denial, HTTP 401/403, or challenges; use an approved export if access is unavailable.

Multiple published start variants are retained as candidates. Totals are selected only when their start labels uniquely match the manifest's named start. Unknown labels or conflicting totals remain blank with `metadata_scope_status=review_required`; no lower/upper mixture is silently accepted. The parser was also exercised against the mapped official overview sections; ambiguous start totals remain withheld. All 100 rows have official route mappings and acquired GPX; full-itinerary geometry remains subject to review. No trip-report metrics or composite GPX are synthesized.

## Import existing normal browser downloads

Original GPX files, minimal overview captures, the accepted agreement and hashed download receipts are under `private_data/browser_downloads/`. The standalone importer reuses the existing ingestion implementation, makes no network requests, validates receipt/file hashes and exact observed source URLs, and preserves the frozen review flags. It does not treat participant candidates or an approach component as a completed custom route.

```bash
python outputs/block1_scraper.py --manifest outputs/route_manifest.csv \
  --out private_data/raw --contact local-private-project --offline \
  --download-agreement-accepted --browser-download-dir private_data/browser_downloads
python scripts/audit_phase2.py --data-root private_data/raw
```

The import exits 2 while the 100-ready gate is unmet; the integrity audit exits 0 when the saved snapshot is internally consistent. Source GPX is copied without editing. Per-selection sidecars retain the acquisition receipt, original-file SHA-256, overview hash, validation results, sequence endpoints and segment-safe horizontal distance. These distances are coverage diagnostics, not substituted published itinerary totals or Phase 3 features.

## Approved export adapter

A reviewed owner-approved export can be ingested **without network access**. Put `approved_export.json` and its GPX files in a private directory. The JSON contract is:

```json
{
  "schema_version": "1.0.0",
  "manifest_sha256": "COPY_CURRENT_HASH_FROM_PROJECT_CONFIG",
  "permission_evidence": "Private permission reference describing this export's allowed use",
  "records": []
}
```

Each record must contain the following fields; the empty array above is a schema illustration, not a usable route dataset:

| Fields | Requirements |
|---|---|
| `route_id` | One known selection ID, at most once |
| `reviewer`, `review_date` | Identifiable reviewer and YYYY-MM-DD date |
| `source_references` | Nonempty array of supporting HTTPS URLs |
| `metadata_evidence`, `geometry_evidence` | References explaining metric scope and complete track coverage |
| `start_name` | Documented chosen trailhead; matches the manifest if already named |
| `start_policy`, `summit_order`, `descent_policy` | Exact frozen manifest strings; do not silently redefine an itinerary |
| `yds_raw`, `yds_class` | Observed raw `Class ...` text and integer class 1–5; must agree |
| `source_distance_mi`, `source_gain_ft` | Finite positive numbers for the documented complete itinerary |
| `exposure_raw`, `rockfall_raw`, `route_finding_raw`, `commitment_raw` | Low, Moderate, Considerable, High or Extreme; no invented defaults |
| `gpx_file`, `gpx_sha256` | Relative path inside the export directory and actual file SHA-256 |
| `itinerary_verified`, `dry_summer_verified` | JSON booleans, supported by review evidence |
| `conditions_evidence` | Required when `dry_summer_verified` is true |

Kiener's and the custom Chicago Basin combination are excluded. Individual Chicago Basin routes must include Needleton approach/return; North Eolus connector totals must not be mislabeled as full-route totals. A GPX is not proof of snow-free climbing. Assembly is supplied and reviewed by the curator; the adapter does not stitch components or bridge gaps.

```bash
python outputs/block1_scraper.py --manifest outputs/route_manifest.csv \
  --out private_data/raw --contact YOUR_RESEARCH_CONTACT \
  --offline --curated-file private_data/approved_export/approved_export.json
python scripts/audit_phase2.py --data-root private_data/raw
```

Offline import does not need live-download execution flags. It requires documented permission in the export itself; it does not imply raw redistribution/publication rights. Valid records are imported even when others fail. Unprovided rows are `awaiting_approved_export`; invalid records are `curation_error`. The importer preserves observed/effective grades, provenance and checksums. Absolute paths, directory escapes, mismatched hashes and itinerary changes are rejected.

## Snapshot and Phase 3 handoff

Ingestion writes `manifest_snapshot.csv`, `run_provenance.json`, `catalog.json` when collected, cached responses, GPX/sidecars, `route_status.csv`, `missing_routes.csv`, `review_required.csv`, and `run_summary.json`. CSV writes are atomic. Raw response caches and resumed GPX must match their URL/hash provenance. An individual ordinary HTTP/parser error is reported while other selections continue; access blocks end the live run.

The Phase 2 audit verifies frozen IDs/scope, summary counts, every downloaded file's checksums, and reparsed XML point/elevation coverage. A successful audit means **snapshot integrity**, not dataset completeness. `phase3_dataset_ready` becomes true only with 100 preliminary eligible selections and validated file provenance. Phase 3 then checks sampling, gaps, noise, distance/gain discrepancies and near-duplicate overlap before features are trusted. Do not use timestamps, speed or elapsed time as predictors.

After new collection/review evidence, update the contract and roadmap, rerun audit/validation/tests, and regenerate the existing bundle. Do not publish private permission references or raw source tracks without explicit redistribution rights.
