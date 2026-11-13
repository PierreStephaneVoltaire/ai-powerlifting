# LiteLLM gateway for all AI

Goal: register the ChatGPT subscription once in LiteLLM, add OpenRouter and any OpenAI-compatible providers there, and point every AI caller at LiteLLM. LiteLLM is exposed at `llm.nolift.training`. Its credentials live in AWS Secrets Manager.

## Facts established

- There is no existing LiteLLM deployment or chart in any repo or in the cluster. The old discord-bot config pointed at `litellm.ai-platform.svc:4000`; that namespace is gone. Use the official image.
- LiteLLM `chatgpt/` provider (>= 1.106, needs the `mcp` extra; verify the proxy image ships it):
  - holds the ChatGPT subscription through an OAuth device login
  - stores the token in `$CHATGPT_TOKEN_DIR/auth.json`, which lasts about 10 days and is refreshed automatically
  - serves `/v1/responses`, and `/v1/chat/completions` bridged to it
  - Docs: https://docs.litellm.ai/docs/providers/chatgpt
- All powerlifting AI runs through the Coach's Codex worker: glossary, lift-profiles, analytics-ai reports, chat, imports, budget.
- The Coach already supports `auth = "api_key"` providers with `base_url`. Codex is configured with `model_providers.<name>` (`wire_api = "responses"`, `env_key = COACH provider key env`; see `src/services/coach/model.py`).
- The Cloudflare tunnel ingress and DNS live in root `terraform/modules/tunnel`. Routes are `terraform/k8s/network/routes.tf`. Mesh policies are `terraform/k8s/app/mesh.tf`.

## Changes

### 1. Secrets Manager: root `terraform/` (AWS stack)

- `aws_secretsmanager_secret` `powerlifting/litellm`, with a version whose JSON holds:
  - `master_key`: `random_password`, prefixed `sk-`
  - `provider_keys`: new sensitive var `litellm_provider_keys`, `map(string)` of provider name to API key
- Never delete existing AWS resources.

### 2. Tunnel and DNS: root `terraform/modules/tunnel` + `main.tf`

- New var `llm_domain` = `llm.nolift.training`.
- Add an ingress rule (same edge origin as the app) and a CNAME, like `auth`.

### 3. LiteLLM workload: `terraform/k8s/app/litellm.tf` (new file)

- Providers are defined once, aliases group deployments, fallbacks run between aliases. The app only refers to aliases.
  - `litellm_providers`: `map(object({ type, base_url? }))`, type is `chatgpt`, `openrouter` or `openai`
  - `litellm_models`: alias to `list({ provider, model, weight? })`, load-balanced across deployments
  - `litellm_fallbacks`: alias to ordered list of fallback aliases
- Rendered `config.yaml`:
  - `credential_list`: one entry per provider with a key or `base_url`; `api_key` is `os.environ/<PROVIDER>_API_KEY`. The `chatgpt` provider has none and uses the device-login token.
  - `model_list`: one entry per alias deployment, `model_name` is the alias, `litellm_credential_name` is the provider, `model_info.mode: responses`
  - `router_settings.fallbacks` only when fallbacks are set
  - `general_settings.master_key: os.environ/LITELLM_MASTER_KEY`
- A k8s Secret holds `LITELLM_MASTER_KEY` and one `<PROVIDER>_API_KEY` per `provider_keys` entry.
- Deployment `litellm`: pinned `ghcr.io/berriai/litellm:v1.108.8`, 1 replica (single-writer token), `CHATGPT_TOKEN_DIR=/data/chatgpt` on a 1Gi local-path PVC, port 4000, `/health/liveliness` probes, memory 256Mi request and 1Gi limit, ambient mesh, ServiceAccount `litellm`.
- Service `litellm` on :4000, port name `http`. No database: master-key auth only.

### 4. Mesh and route

- `mesh.tf`: an `allowed-callers` / `waypoint-only` pair for `litellm`, following the existing pattern. Callers: `pl-coach`, and the edge gateway for public `llm.nolift.training`.
- `network/routes.tf`: HTTPRoute `llm_domain` → `litellm:4000`. It goes directly to LiteLLM, not through oauth2-proxy; LiteLLM keys are the auth. New var `llm_domain` in the network stack.

### 5. Coach cutover: `terraform/coach`

- `provider-keys.tf`: `COACH_PROVIDER_KEYS = merge(var.coach_provider_api_keys, { litellm = <master_key> })`.
- tfvars: `coach_providers = { litellm = { auth = "api_key", base_url = "http://litellm.powerlifting.svc.cluster.local:4000/v1", max_concurrent = 4 } }`. Every `operation_ai` and `conversation_ai` entry uses provider `litellm` and an alias (`pl-standard`, `pl-light`, `pl-documents`), efforts unchanged.
- The ChatGPT login path in the Coach stays in code but is unused once no provider has `auth = "chatgpt"`.

### 6. Secrets plumbing

- The OpenRouter key comes from the operator's `~/.bashrc` (`OPENROUTER_API_KEY`). It goes into `litellm_provider_keys` (`{"openrouter": "<key>"}`) in the gitignored root tfvars and the `LITELLM_PROVIDER_KEYS` GitHub secret; never print it.
- Update the tfvars and GitHub secrets the pipeline uses (`K8S_TFVARS`, `LITELLM_PROVIDER_KEYS`, `COACH_TFVARS`) with `gh secret set` from the local files.

## Operator step after deploy (one time)

1. Enable device-code login in ChatGPT security settings.
2. Run `kubectl -n powerlifting exec -it deploy/litellm -- python -c "from litellm.llms.chatgpt.authenticator import Authenticator; Authenticator().get_access_token()"`.
3. Open the URL and enter the code. The token persists on the PVC.

## Order

1. Root stack: secret, tunnel, DNS.
2. LiteLLM workload, mesh, route.
3. Operator device login.
4. Coach cutover (tfvars).

Until step 3 is done the Coach must stay on the direct `chatgpt` provider. Keep the cutover tfvars as a separate, clearly marked change.

## Out of scope

- The IF agent API in the parent repo also uses a direct ChatGPT login. It is a protected live service, so the operator does that cutover.
