# Current-Program Past Block Analytics

## Summary

- Use only the `current` program as the source of truth. Do not scan forks, archived versions, or historical program versions.
- Derive all blocks from `current.sessions[*].block`, with `current` treated as the latest block and non-current block labels treated as past blocks.
- Keep this in `/analysis` as tabs: `Weekly`, `Past Blocks`, and `Lifetime Compare`.

## Stage 1: Data Mapping

- Add a backend block index built from `getProgram(pk, 'current')` only.
- For each block, compute block key, label, first and last workout date, week range, completed/planned sessions, phases for that block, source fingerprint, and data-quality flags.
- Link completed competitions from `current.competitions` to blocks by:
  - competition date inside the block date range,
  - otherwise completed competition within 30 days after the block's last workout,
  - closest eligible competition if multiple candidates exist.
- If no competition maps, mark the block `training_only`; still analyzable, but exclude it from default comp-block comparisons.
- Surface missing data: no linked comp, missing comp results/bodyweight/post-meet report, missing T-minus-1 projection/PRR, missing start maxes, sparse bodyweight/wellness/diet, missing glossary muscle/fatigue metadata.

## Stage 2: Past Block Analysis

- Add `GET /api/analytics/blocks` for the current-program block list.
- Add `GET /api/analytics/blocks/:blockKey/analysis?refresh=false`.
- Generate a `BlockAnalysisBundle` from only sessions in that block, with block-local phases and `ref_date = block.end`.
- Reuse deterministic analytics: full-block weekly analysis, INOL, ACWR, Banister, fatigue, monotony/strain, specificity, taper quality, volume landmarks, compliance, deloads, exercise stats, and muscle-map averages.
- Add historical-only outputs: start/end strength, comp outcome, actual DOTS/IPF GL, projection accuracy/PRR, and what data was missing.
- Cache by block source fingerprint in `if-powerlifting-analysis-cache`; past blocks should not expire quickly because completed blocks rarely change.

## Stage 3: Lifetime Comparison

- Add `POST /api/analytics/block-comparison` with selected `blockKeys` plus an `includeCurrentFullBlock` option.
- Default selection: all past blocks linked to completed competitions; optionally include training-only blocks and the latest full current-block cache.
- Compare cached block summaries, not raw sessions, for token efficiency.
- Show inter-block trends: actual/e1RM progression, total/DOTS/IPF GL, INOL, ACWR, volume, muscle-map volume averages, compliance, taper/fatigue shape, projection accuracy, and exercise/muscle ROI signals.
- Estimate volume tolerance/MRV-style patterns only when enough comp-linked blocks exist; otherwise show low confidence and required missing sample size.

## UI Plan

- `Weekly`: keep the current weekly/full-current-block analysis.
- `Past Blocks`: block list with linked comp, data-quality badges, cache status, generate/refresh/view actions.
- `Lifetime Compare`: block selector, `All comp blocks` preset, optional `Include training-only`, and comparison charts/tables.
- Empty states cover no past blocks, no comp-linked blocks, ambiguous comp mapping, missing comp results, and insufficient data for correlation/tolerance estimates.

## Test Plan

- Unit test current-program block discovery from `session.block`.
- Unit test competition mapping: in-range, within 30 days after block, multiple candidates, no comp, skipped comp, missing results.
- Unit test source fingerprints and cache reuse/refresh.
- Unit test start/end max fallback logic.
- Integration test past-block analysis with missing glossary/bodyweight/wellness data.
- Integration test lifetime comparison with zero, one, and multiple selected blocks.
- Frontend tests for tabs, block selection, empty states, cached/generated status, and missing-data badges.

## Assumptions

- The current program contains all historical and current blocks.
- No code should read forks or archived program versions for this feature.
- Training-only blocks are valid for past-block analysis but excluded from default lifetime comp comparisons.
