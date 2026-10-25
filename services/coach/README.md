# Coach

A lightweight AI Coach for the portal, plus a Discord relay. It will replace
the external agent API once that system is decommissioned.

- `services/coach/` (`pl-coach`) runs on a ChatGPT subscription through the pinned
  `openai-codex` SDK.
  - `POST /v1/jobs`, `GET /v1/jobs/{id}[/result]` and `POST /v1/jobs/{id}/cancel`
    implement the domain-job contract that the Powerlifting Services and backend
    already use. The Coach calls the operation, answers each `needs_inference`
    challenge with the model, checks the answer against the challenge schema,
    then resumes the execution.
  - `POST /v1/conversations/{id}/turns` handles chat. Each Conversation keeps one
    Codex thread, and every non-internal operation in `services/operations/` is
    exposed as an MCP tool for the Person and Athlete on that turn.
- `services/coach_discord/` (`pl-coach-discord`) is the Discord Interactions
  endpoint. It verifies the request signature, defers the reply, forwards
  `/coach` to the Coach and edits the reply when the answer is ready.
  `/coach-reset` starts a new Conversation for the channel.

## Build and deploy

Both images are Packer templates (`docker/powerlifting-coach-agent.pkr.hcl`,
`docker/powerlifting-coach-discord.pkr.hcl`). CI (`.github/workflows/build-images.yml`,
job `build-coach`) builds them on
`services/**` changes and pushes `:latest` and `:<sha>` to
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

## Discord cutover

1. Register the commands with `python -m services.coach_discord.register [guild_id]`.
   This creates or updates only `/coach` and `/coach-reset`.
2. Expose `pl-coach-discord:8000/interactions` publicly (Cloudflare lives in the
   root repo).
3. Set that URL as the bot's Interactions Endpoint URL.

After step 3, Discord delivers **all** of that application's slash commands to the
relay rather than to the gateway bot.
