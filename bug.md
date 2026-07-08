# Bug List

## Fixed
- DOTS calculator returns 154M instead of ~430: meta values (target_squat_kg, target_bench_kg, target_dl_kg, current_body_weight_kg) returned as strings from program_get fission handler due to json.dumps(default=str) on Decimal values. Fixed with recursive _coerce_decimals in program_get/core.py. Also added Number() coercion in DotsCalculator.tsx.
- Competitions page blank: was fission pod_competition cold-start delay. Verified 196 competitions returned correctly now.
- Maxes endpoint returning empty: was fission pod_maxes cold-start delay. Verified targets: squat 220, bench 145, deadlift 250, total 615.
- Analysis page blank/hanging: was originally "fixed" with a 15s AbortController timeout in invokeLambda, but that timeout became the root cause of failures (killed long-running Fission calls like dataset loading). Timeout has been REMOVED — nginx handles request timeouts (5-10 min). Frontend manifest failure is non-fatal - sections poll independently.

## Known Issues (Fix Forward)
- pod_analysis OOM when loading 782MB OpenPowerlifting CSV. Increased memory limit from 4Gi to 8Gi and changed low_memory=False to low_memory=True. ECR images wiped and CI triggered to rebuild with fix.
- pod_analysis background thread may silently die without setting _df_error. The warm_cache() thread starts at module import but can fail without logging. Need to investigate why the daemon thread dies. Possible cause: unhandled exception in _parse_csvs that doesn't get caught by the except clause.
- Session design crash: needs investigation once pod_analysis is back up. Likely related to null data from failed analysis calls.
- ECR DNS resolution intermittent (dial tcp: lookup ... Try again). Pods that need to pull new images may fail. Workaround: delete pod and let it retry until DNS resolves.
- Ranking percentile needs retry polling on frontend. Added 5-attempt retry with 15s interval in Dashboard.tsx.
