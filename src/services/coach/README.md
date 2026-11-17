# Coach

`src/services/coach/` (`pl-coach`) is the domain-job broker. It runs Codex on a ChatGPT
subscription (or an API-key provider) through the pinned `openai-codex` SDK. It
has no chat, no conversation state and no tools of its own.

## HTTP

All routes except `/health` need the `X-Person-Pk` header.

- `POST /v1/jobs` accepts `{"kind": "domain", "payload": {"operation", "arguments", "athlete"}}`
  and returns 202 with the job. Any other `kind` returns 422.
- `GET /v1/jobs/{id}` returns the job.
- `GET /v1/jobs/{id}/result` returns the job: 200 when finished, 202 while queued or running.
- `POST /v1/jobs/{id}/cancel` cancels a running job.
- `GET /health` returns the status and the operation count.

A job has one of the statuses `queued`, `running`, `succeeded`, `failed`, `cancelled`
or `uncertain`. Jobs still queued or running when the Coach starts become `uncertain`.

The Coach calls the operation on its Powerlifting Service. For each `needs_inference`
challenge it asks the model, checks the answer against the challenge schema, then
resumes the execution. `template_evaluate` also gets the athlete's lifetime report
from S3 (`POWERLIFTING_S3_BUCKET`) as a file in the model workspace.

## State

Job records live in `coach.sqlite3` (table `jobs`) in `COACH_STATE_DIR`. Codex login
lives in `CODEX_HOME` on the `pl-coach-state` volume.

## Configuration

`COACH_PROVIDERS` (provider name to `auth`, `max_concurrent`, `base_url`),
`COACH_PROVIDER_KEYS`, `COACH_OPERATION_AI` (model, provider and effort for every AI
operation), `COACH_STATE_DIR`, `PL_SERVICE_URL_TEMPLATE`, `PL_OPERATIONS_DIR`,
`PL_PERMISSIONS_PATH`, `POWERLIFTING_S3_BUCKET`.

## Build and deploy

Packer template: `docker/powerlifting-coach-agent.pkr.hcl`. CI
(`.github/workflows/build-images.yml`, job `build-coach`) pushes it to
`if-powerlifting-coach-agent`. For a manual build, run
`scripts/build_coach_images.sh agent`. The Kubernetes resources are in
`terraform/coach/`.

## One-time login

```bash
kubectl exec -it -n <namespace> deploy/pl-coach -- python -m services.coach.login
```

The login is stored on `pl-coach-state` and survives restarts.
