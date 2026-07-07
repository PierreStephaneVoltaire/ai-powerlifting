# Bugs / issues to revisit

- `packages/types/index.ts` / `backend/src/db/schema_glossary.json`: the domain "Glossary" concept (the Athlete's exercise dictionary — exercises → fatigue profiles) collides with "glossary" as the name of the ubiquitous-language file (`CONTEXT.md`). Consider renaming the domain concept to **Exercise Library** (or **Exercise Dictionary**) to remove the collision. See `CONTEXT.md`. (Architectural, not a runtime bug — deferred.)
- `AGENTS.md` "Known intentional mismatches" #1 and `docs/ARCHITECTURE.md` "Current rough edges" #1 describe a frontend-local RPE-table / conservative-percent "trend max" that "can legitimately differ" from backend `current_maxes`. Owner ruling: any frontend/backend max disparity is a bug, fixed by a shared function — there is no legitimate divergence to protect. The entry is stale; the "trend maxima" refer to the trend chart's weekly aggregation (`frontend/src/pages/AnalysisPage.tsx`, `frontend/src/utils/rpe.ts`), not a competing max measure. See `CONTEXT.md` Performance invariant. (Doc-only — deferred.)

---

## Stale open entries — already fixed in code (commit db66ea1, 2026-07-07)

The following were listed as "open" in this file but the fix was already committed in `db66ea1` ("regressions"). Removing from the open list. Code references for the record:

- **Competitions not pulling from `program.competitions`**: fixed in `backend/src/controllers/competitionController.ts` — `getUserCompetitions` / `patchUserCompetition` / `completeUserCompetition` go through the new `health_list_competitions` Fission function. New Fission function lives at `lambda/pod_competition/handlers/health_list_competitions/` and reads `if-powerlifting-user-competitions` directly. New routes `GET /api/competitions`, `PATCH /api/competitions/:masterId`, `POST /api/competitions/:masterId/complete` added to `backend/src/routes/competitions.ts`. `POWERLIFTING_USER_COMPETITIONS_TABLE` + `POWERLIFTING_MASTER_COMPETITIONS_TABLE` added to `pl_common_env` in `terraform/k8s-fission-powerlifting.tf`. **After image rebuild + Fission rollout** the frontend's `useCompetitionsStore.loadAll()` should return real data.
- **Percentile rankings not pulling from S3**: fixed in `lambda/pod_analysis/resources.yaml` (`s3_read: true`) and `_ensure_dataset_downloaded()` helper added to `analyze_powerlifting_stats`, `powerlifting_ranking_percentile`, `powerlifting_filter_categories`. **After image rebuild of `pod_analysis`** the stats tools will download the OpenPowerlifting CSVs from S3 on first call.
- **DOTS calculator initial value wrong**: fixed in `frontend/src/components/tools/DotsCalculator.tsx` (useMemo → useEffect for the initialize-from-maxes block).
- **Profile `display.toFixed` crash**: fixed in `frontend/src/pages/ProfilePage.tsx` (Number/Number.isFinite coercion before toFixed on all four weightValue/DOTS call sites; signature widened to `number | string | null | undefined`).
- **Analysis page error visibility**: fixed in `frontend/src/pages/AnalysisPage.tsx` (error card with retry + per-section status dump). The "no data comes in" root cause is a separate issue — see next section.

---

## Open — root cause for "no data on analysis page"

- Analysis page: no data comes in. Live-evidence step done (see 2026-07-07 entries below): root cause was a different missing-dep class, not the `health_get_program` cache. **Code fix shipped this session** (see below). Need to rebuild `pod_analysis` and re-verify in the browser.

## Fixed 2026-07-07

- **glossary page blank + session-design page empty (same root cause)**: `pod_glossary` Fission image was missing `rapidfuzz`. `glossary_store.py` does `from rapidfuzz import fuzz` at module level; the `pl-glossary` layer had no pip deps declared. DesignerPage's `useEffect(() => api.fetchGlossary().then(setGlossary).catch(console.error), [])` swallows the 500 in `.catch(console.error)`, so the page doesn't *crash* but renders an empty exercise picker — operator-reported as "crash". Fixed in `lambda/fission_layers.py` (`pl_glossary` layer now declares `rapidfuzz==3.10.1`) and in the build script (see below). After image rebuild + Fission rollout of `pod_glossary`, both pages populate.
- **`pod_analysis` `analysis_section` / `weekly_analysis` / `regenerate_analysis` 500ing on `ModuleNotFoundError: No module named 'scipy'`**: same bug class as glossary. 5 of 13 analysis handlers import `from scipy.stats import kendalltau, theilslopes`; the tool's `requirements.txt` only declared `pandas` + `numpy`. Fixed by the build-script fix below.
- **Per-handler `requirements.txt` files were dead code**: the build script `lambda/fission-deploy.py` → `fission_layers.requirements_for()` only ever read `lambda/<tool>/requirements.txt` at the tool root, never `lambda/<tool>/handlers/<name>/requirements.txt`. 76 per-handler `requirements.txt` files existed in the repo, all hand-maintained, and were silently ignored. Fixed in `lambda/fission_layers.py`: `requirements_for` now also scans `handlers/*/requirements.txt` (via a small `_read_requirements_file` helper that handles the `# comment` / empty-line cases identically to the tool-root case). Verified by re-running `python3 lambda/fission-deploy.py` and inspecting the rebuilt zips — `pod_analysis`, `pod_glossary`, `pod_import`, `pod_competition`, `pod_training_program`, `get_analysis_markdown` all now carry the right deps. **NB:** anyone running this build must `rm -rf utils/powerlifting-app/lambda/__pycache__` first, or they'll execute a stale `.pyc` that hides the fix. Stale `.pyc` is exactly what bit me mid-session: the first re-run of `fission-deploy.py` after the code change produced a zip missing the new deps because the deploy script imported a cached `fission_layers` from before the edit.
- **`pod_import` `import_parse_file` 500ing on any xlsx upload**: `import openpyxl` was lazy-imported inside the handler (so module load succeeded), but the per-handler `requirements.txt` was an empty file. Fixed by writing `openpyxl` into `lambda/pod_import/handlers/import_parse_file/requirements.txt`; the build-script fix above now picks it up.

---

## What still needs operator action (not code)

1. `rm -rf utils/powerlifting-app/lambda/__pycache__` (clear stale `.pyc`).
2. `cd utils/powerlifting-app/lambda && python3 fission-deploy.py` (rebuild the 44 zips — already done in this session).
3. Packer rebuild for the affected images: `pod_glossary`, `pod_analysis`, `pod_import`, `pod_competition`, `pod_training_program`, `get_analysis_markdown` (all tools that gained new deps from per-handler `requirements.txt`).
4. Push rebuilt images to ECR, then `terraform apply -target=kubectl_manifest.pl_functions` (main repo) to roll the Fission function CRDs — the `source_sha` in `k8s-fission-powerlifting.tf` will already have changed because the zips changed, so a plain `terraform plan` will show the diff. Pods will pull the new image and pick up the new deps.

The "operator action" items above are the only things left to actually clear the symptoms in the browser. Code-side, this session is done.
