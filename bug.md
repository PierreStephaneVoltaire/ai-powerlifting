# Bug List

## Fixed
- DOTS calculator returns 154M instead of ~430: meta values (target_squat_kg, target_bench_kg, target_dl_kg, current_body_weight_kg) returned as strings from program_get fission handler due to json.dumps(default=str) on Decimal values. Fixed with recursive _coerce_decimals in program_get/core.py. Also added Number() coercion in DotsCalculator.tsx.
- Competitions page blank: was fission pod_competition cold-start delay. Verified 196 competitions returned correctly now.
- Maxes endpoint returning empty: was fission pod_maxes cold-start delay. Verified targets: squat 220, bench 145, deadlift 250, total 615.
- Analysis page blank/hanging: invokeLambda had no timeout, so pod_analysis ImagePullBackOff caused infinite hang in manifest endpoint. Added 15s AbortController timeout to invokeLambda. Made frontend manifest failure non-fatal - sections now poll independently.

## Known Issues (Fix Forward)
- pod_analysis fission pod in ImagePullBackOff due to ISP issues blocking ECR image pulls. Image exists in ECR (verified via aws ecr describe-images). Cannot fix without ISP resolution. Analysis sections that depend on pod_analysis will show errors until pod can pull.
- Session design crash: needs investigation once pod_analysis is back up. Likely related to null data from failed analysis calls.
