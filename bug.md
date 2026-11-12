
## Anonymous backend requests default to the operator athlete (2026-11-12)
Inside the cluster, `GET http://powerlifting-app-backend:3005/api/programs/current` with no Authorization header returns the `operator` program (`resolvePk` falls back to `operator`). oauth2-proxy blocks this at the edge today, so it is not reachable publicly, but any future `--skip-auth-route` (e.g. for signed-out profile search) would expose it. Anonymous requests should resolve to no athlete.
