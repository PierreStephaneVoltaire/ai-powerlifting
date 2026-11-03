# Coach

A lightweight AI Coach for the portal, plus a Discord bot. Together they replace
the external agent API.

- `src/services/coach/` (`pl-coach`) runs on a ChatGPT subscription through the pinned
  `openai-codex` SDK.
  - `POST /v1/jobs`, `GET /v1/jobs/{id}[/result]` and `POST /v1/jobs/{id}/cancel`
    implement the domain-job contract that the Powerlifting Services and backend
    already use. The Coach calls the operation, answers each `needs_inference`
    challenge with the model, checks the answer against the challenge schema,
    then resumes the execution.
  - `POST /v1/conversations/{id}/turns` handles chat. Each Conversation keeps one
    Codex thread, and every non-internal operation in `src/services/operations/` is
    exposed as an MCP tool for the Person and Athlete on that turn.
- `src/services/coach_discord/` (`pl-coach-discord`) is the Discord bot, ported
  from the agent API's channel listener. Registrations (bot token, channel) live in
  the `if-webhooks` table under the `powerlifting` partition, in the same item
  format the agent API used. On startup it opens one gateway websocket per bot
  token for every active registration. Each human message (or edit) in a
  registered channel goes to the Coach as the sender's Person, mapped from
  `DISCORD_PERSONS` and the operator's Discord ID, and the answer is posted as a
  reply. `/coach-reset` starts a new Conversation for the channel. Nothing calls
  the bot from outside the cluster.

## Build and deploy

Both images are Packer templates (`docker/powerlifting-coach-agent.pkr.hcl`,
`docker/powerlifting-coach-discord.pkr.hcl`). CI (`.github/workflows/build-images.yml`,
job `build-coach`) builds them on
`src/services/**` changes and pushes `:latest` and `:<sha>` to
`if-powerlifting-coach-agent` and `if-powerlifting-coach-discord`. Those ECR
repositories are in the main `terraform/` state's `ecr` module, applied by CI.
For a manual Packer build, run `scripts/build_coach_images.sh agent discord`.

`terraform/coach/` has its own state (`powerlifting-app/coach/terraform.tfstate`).
It holds only Kubernetes resources: the `pl-coach-state` PVC and both
Deployments and Services. CI cannot reach the cluster, so apply it locally. It
reads each image digest from the `latest` tag, so a rollout is a new `:latest`
followed by:

```bash
cd terraform/coach
terraform init -backend-config=backend.tfvars
terraform plan -out=coach.plan && terraform apply coach.plan
```

Every variable is required and has no default. Environment values live in the
gitignored `terraform.tfvars` (template: `terraform.tfvars.example`), and the
state location lives in the gitignored `backend.tfvars`. Secrets are referenced by
name and never copied.

## One-time login

```bash
kubectl exec -it -n <namespace> deploy/pl-coach -- python -m services.coach.login
```

The login is stored on `pl-coach-state` and survives restarts.

## Discord registrations

The only HTTP routes besides `/health` manage registrations. Each needs the
`X-Internal-Token` header.

- `POST /v1/servers` with `{"label", "bot_token", "channel_id"}` stores the
  registration and starts listening immediately.
- `GET /v1/servers` lists registrations without their tokens.
- `DELETE /v1/servers/{webhook_id}` stops listening and marks it inactive.
- `POST /v1/servers/{webhook_id}/restart` reconnects it.
