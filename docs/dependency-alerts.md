# Dependabot review, 2026-11-28

GitHub reported 118 open alerts on `master` at `d0498e7` and 23 open Dependabot pull requests. The counts include separate alerts for a manifest and its lockfile when GitHub flags both. [Repository alerts](https://github.com/PierreStephaneVoltaire/ai-powerlifting/security/dependabot)

| Severity | Open on GitHub | Covered by these dependency changes | Expected remaining from this snapshot |
| --- | ---: | ---: | ---: |
| Critical | 1 | 1 | 0 |
| High | 55 | 48 | 7 |
| Medium | 45 | 32 | 13 |
| Low | 17 | 15 | 2 |

GitHub can confirm closures after the changes reach the default branch and its dependency graph refreshes. Critical alert [#122](https://github.com/PierreStephaneVoltaire/ai-powerlifting/security/dependabot/122) was open at the time of this review.

## Runtime findings

| Component owner | Package | Open critical / high | Local disposition |
| --- | --- | ---: | --- |
| Backend gateway | proxy-addr | 1 / 0 | Express resolves 2.0.8. |
| Frontend HTTP client | axios, form-data | 0 / 15 | Axios resolves 1.21.1, form-data 4.0.6 and follow-redirects 1.16.3. |
| Backend uploads | multer | 0 / 20 | 2.5.0 across the backend manifest and workspace lock. |
| Backend imports and exports | xlsx | 0 / 4 | Removed the unused npm dependency. Rust parses workbooks and Go renders them. The export-to-import check recovered the planned and actual squat loads of 100 and 97.5 kg from the same session. |
| Analytics, imports, rankings | rustls-webpki | 0 / 3 | Each AWS client dependency graph now uses rustls 0.23.46 and rustls-webpki 0.103.16. Removing the legacy HTTPS connector eliminated the parallel 0.21.12 and 0.101.7 copies. |
| Assistant | go-jose, OpenTelemetry, gRPC | 0 / 6 | go-jose 4.1.6, OpenTelemetry and trace 1.47.0, gRPC 1.83.2. The same update resolves x/net 0.58.0, S3 1.97.3 and eventstream 1.7.8. |

## Remaining high findings

The seven projected remaining highs are development dependencies in `src/package-lock.json`. Each has a separate update available. Owners below identify the affected component.

| Component owner | Package | High alerts | Follow-up |
| --- | --- | ---: | --- |
| Workspace build tooling | brace-expansion | 2 | [PR #32](https://github.com/PierreStephaneVoltaire/ai-powerlifting/pull/32) |
| Frontend build tooling | browserslist | 1 | [PR #39](https://github.com/PierreStephaneVoltaire/ai-powerlifting/pull/39) |
| Frontend build tooling | nanoid | 1 | [PR #41](https://github.com/PierreStephaneVoltaire/ai-powerlifting/pull/41) |
| Frontend stylesheet build | postcss | 2 | [PR #37](https://github.com/PierreStephaneVoltaire/ai-powerlifting/pull/37) |
| Frontend stylesheet build | source-map-js | 1 | [PR #33](https://github.com/PierreStephaneVoltaire/ai-powerlifting/pull/33) |

The frontend routing, frontend build and backend gateway owners retain their separate major upgrades for routing, build-tool and module compatibility testing. [React Router 7](https://github.com/PierreStephaneVoltaire/ai-powerlifting/pull/42) · [Vite 7](https://github.com/PierreStephaneVoltaire/ai-powerlifting/pull/46) · [UUID 14](https://github.com/PierreStephaneVoltaire/ai-powerlifting/pull/48)

## Existing image scans

In `ca-central-1`, all 27 Powerlifting ECR repositories had scan-on-push enabled. ECR returned completed scans for 25 `latest` tags. The backend and frontend images each had 4 critical findings in Alpine OpenSSL and zlib, plus 21 high findings. The coach agent had 14 high findings. The two unprefixed coach repositories had no scan for `latest`. These are pre-change image findings. Image owners can track updated digests through the existing ECR scans after publishing.
