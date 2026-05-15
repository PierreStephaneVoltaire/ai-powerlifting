variable "region" {
  description = "AWS Region"
  type        = string
  default     = "ca-central-1"
}

variable "kubeconfig_path" {
  description = "Path to kubeconfig file for k3s cluster"
  type        = string
  default     = "~/.kube/config"
}

variable "kubeconfig_context" {
  description = "Kubernetes context for k3s cluster"
  type        = string
  default     = "default"
}

variable "ecr_repository_prefix" {
  description = "Prefix for ECR repository names"
  type        = string
  default     = "if"
}

variable "openrouter_api_key" {
  description = "OpenRouter API key"
  type        = string
  sensitive   = true
}

variable "discord_token" {
  description = "Discord bot token"
  type        = string
  sensitive   = true
}

variable "alphavantage_api_key" {
  description = "Alpha Vantage API key for financial data"
  type        = string
  default     = ""
  sensitive   = true
}

variable "dynamodb_core_table" {
  description = "DynamoDB table for core directives"
  type        = string
  default     = "if-core"
}

variable "dynamodb_health_table" {
  description = "DynamoDB table for health program"
  type        = string
  default     = "if-health"
}

variable "dynamodb_sessions_table" {
  description = "DynamoDB table for copied health sessions"
  type        = string
  default     = "if-sessions"
}

variable "dynamodb_analysis_cache_table" {
  description = "DynamoDB table for cached powerlifting analysis bundles"
  type        = string
  default     = "if-powerlifting-analysis-cache"
}

variable "dynamodb_finance_table" {
  description = "DynamoDB table for finance portal"
  type        = string
  default     = "if-finance"
}

variable "dynamodb_diary_entries_table" {
  description = "DynamoDB table for diary entries"
  type        = string
  default     = "if-diary-entries"
}

variable "dynamodb_diary_signals_table" {
  description = "DynamoDB table for diary signals"
  type        = string
  default     = "if-diary-signals"
}

variable "dynamodb_proposals_table" {
  description = "DynamoDB table for proposals portal"
  type        = string
  default     = "if-proposals"
}

variable "dynamodb_models_table" {
  description = "DynamoDB table for model metadata registry"
  type        = string
  default     = "if-models"
}

variable "dynamodb_powerlifting_table" {
  description = "DynamoDB table for powerlifting app"
  type        = string
  default     = "powerlifting"
}

variable "dynamodb_user_table" {
  description = "DynamoDB table for user identity mappings and public profiles"
  type        = string
  default     = "if-user"
}

variable "tier_upgrade_threshold" {
  description = "Fraction of context limit before tier upgrade"
  type        = number
  default     = 0.65
}

variable "if_agent_api_model_env" {
  description = "Model, router, tier, and model-adjacent environment variables for the IF agent API pod. ConfigMap values must be strings."
  type        = map(string)
  default     = {}
}

variable "tier_air_limit" {
  description = "Air tier context limit (tokens)"
  type        = number
  default     = 30000
}

variable "tier_standard_limit" {
  description = "Standard tier context limit (tokens)"
  type        = number
  default     = 120000
}

variable "tier_heavy_limit" {
  description = "Heavy tier context limit (tokens)"
  type        = number
  default     = 200000
}

variable "tier_air_preset" {
  description = "OpenRouter preset for air tier"
  type        = string
  default     = "@preset/air"
}

variable "tier_standard_preset" {
  description = "OpenRouter preset for standard tier"
  type        = string
  default     = "@preset/standard"
}

variable "tier_heavy_preset" {
  description = "OpenRouter preset for heavy tier"
  type        = string
  default     = "@preset/heavy"
}

variable "specialist_preset" {
  description = "Default preset for specialist subagents"
  type        = string
  default     = "@preset/standard"
}

variable "specialist_max_turns" {
  description = "Maximum turns per specialist"
  type        = number
  default     = 15
}

variable "thinking_preset" {
  description = "Preset for deep thinking subagent"
  type        = string
  default     = "@preset/general"
}

variable "thinking_max_turns" {
  description = "Maximum turns for deep thinking"
  type        = number
  default     = 20
}

variable "api_model_name" {
  description = "API model identifier for external clients"
  type        = string
  default     = "if-prototype"
}

variable "tokenizer_model" {
  description = "Tokenizer model for tiktoken"
  type        = string
  default     = "gpt-4"
}

variable "embedding_model" {
  description = "Embedding model for vector storage"
  type        = string
  default     = "all-MiniLM-L6-v2"
}

variable "suggestion_model" {
  description = "Model for suggestions and title generation"
  type        = string
  default     = "mistralai/mistral-nemo"
}

variable "directive_rewrite_model" {
  description = "Model for directive content rewriting"
  type        = string
  default     = "openrouter/@preset/heavy"
}

variable "model_router_model" {
  description = "Fast model for subagent routing"
  type        = string
  default     = "anthropic/claude-haiku-4.5"
}

variable "health_helper_model" {
  description = "Cheaper model for narrow powerlifting helper flows"
  type        = string
  default     = "openai/gpt-5.4-mini"
}

variable "condenser_model" {
  description = "Model for conversation condensation"
  type        = string
  default     = "openrouter/@preset/general"
}

variable "reflection_model" {
  description = "Model for reflection engine"
  type        = string
  default     = "openrouter/@preset/general"
}

variable "orchestrator_subagent_model" {
  description = "Model for orchestrator subagents"
  type        = string
  default     = "openrouter/@preset/standard"
}

variable "orchestrator_analysis_model" {
  description = "Model for parallel analysis"
  type        = string
  default     = "openrouter/@preset/air"
}

variable "orchestrator_synthesis_model" {
  description = "Model for synthesis of analysis results"
  type        = string
  default     = "openrouter/@preset/standard"
}

variable "research_agent_model" {
  description = "Model for research agent"
  type        = string
  default     = "openrouter/@preset/research"
}

variable "diary_signal_model" {
  description = "Model for diary signal computation"
  type        = string
  default     = "openrouter/@preset/air"
}

variable "orchestrator_max_turns" {
  description = "Maximum turns per orchestrator subagent"
  type        = number
  default     = 15
}

variable "orchestrator_analysis_max_turns" {
  description = "Maximum turns for analysis subagents"
  type        = number
  default     = 10
}

variable "message_window" {
  description = "Recent messages for context"
  type        = number
  default     = 8
}

variable "context_condense_threshold" {
  description = "Context size threshold for condensation"
  type        = number
  default     = 250000
}

variable "tool_output_char_limit" {
  description = "Max chars for tool output before SDK truncation (default SDK is 50000)"
  type        = number
  default     = 200000
}

variable "channel_debounce_seconds" {
  description = "Message batching window (seconds)"
  type        = number
  default     = 5
}

variable "llm_reasoning_effort" {
  description = "Reasoning effort for the main agent LLM (high/medium/low)"
  type        = string
  default     = "high"
}

variable "channel_max_chunk_chars" {
  description = "Max chars per response chunk"
  type        = number
  default     = 1500
}

variable "heartbeat_enabled" {
  description = "Enable heartbeat system"
  type        = bool
  default     = true
}

variable "heartbeat_idle_hours" {
  description = "Hours of inactivity before heartbeat"
  type        = number
  default     = 6.0
}

variable "heartbeat_cooldown_hours" {
  description = "Hours between heartbeats on same channel"
  type        = number
  default     = 6.0
}

variable "heartbeat_quiet_hours" {
  description = "UTC time range to skip heartbeats"
  type        = string
  default     = "23:00-07:00"
}

variable "reflection_enabled" {
  description = "Enable reflection engine"
  type        = bool
  default     = true
}

variable "reflection_periodic_hours" {
  description = "Hours between periodic reflections"
  type        = number
  default     = 6.0
}

variable "reflection_post_session_min_turns" {
  description = "Minimum turns before post-session reflection"
  type        = number
  default     = 5
}

variable "reflection_threshold_uncategorized" {
  description = "Uncategorized facts to trigger reflection"
  type        = number
  default     = 20
}

variable "terminal_network" {
  description = "Docker network for terminals"
  type        = string
  default     = "if-terminal-net"
}

variable "terminal_idle_timeout" {
  description = "Seconds before idle terminal cleanup"
  type        = number
  default     = 3600
}

variable "terminal_startup_timeout" {
  description = "Seconds to wait for terminal startup"
  type        = number
  default     = 30
}

variable "terminal_max_containers" {
  description = "Maximum concurrent terminal containers"
  type        = number
  default     = 20
}

variable "terminal_storage_gb" {
  description = "Storage size for terminal workspace (GB)"
  type        = number
  default     = 10
}

variable "health_program_pk" {
  description = "Partition key for health program storage"
  type        = string
  default     = "operator"
}

variable "if_user_pk" {
  description = "Default user PK for infrastructure tables"
  type        = string
  default     = "operator"
}

variable "diary_ttl_days" {
  description = "TTL for diary entries (days)"
  type        = number
  default     = 3
}

variable "diary_signal_compute_interval_hours" {
  description = "Interval for automatic signal computation (hours)"
  type        = number
  default     = 6.0
}

variable "log_level" {
  description = "Logging level"
  type        = string
  default     = "INFO"
}

variable "storage_class" {
  description = "Kubernetes storage class for persistent volumes"
  type        = string
  default     = "local-path"
}

variable "node_name" {
  description = "Node name for local-path provisioner with Immediate binding"
  type        = string
  default     = "sirsimpalot-g5-5000"
}

variable "data_storage_gb" {
  description = "Storage size for main API data (GB)"
  type        = number
  default     = 10
}

variable "sandbox_storage_gb" {
  description = "Storage size for sandbox files (GB)"
  type        = number
  default     = 5
}

variable "conversations_storage_gb" {
  description = "Storage size for conversation persistence (GB)"
  type        = number
  default     = 5
}

variable "facts_storage_gb" {
  description = "Storage size for facts database (GB)"
  type        = number
  default     = 2
}

variable "portal_memory_mb" {
  description = "Memory limit for portal backends (MB)"
  type        = number
  default     = 1024
}

variable "portal_cpu_millicores" {
  description = "CPU limit for portal backends (millicores)"
  type        = number
  default     = 500
}

variable "api_memory_mb" {
  description = "Memory limit for main API (MB)"
  type        = number
  default     = 5120
}

variable "api_memory_request_mb" {
  description = "Memory request for main API (MB) — used for scheduling; should reflect steady-state usage after dataset warm-up"
  type        = number
  default     = 2048
}

variable "api_cpu_request_millicores" {
  description = "CPU request for main API (millicores)"
  type        = number
  default     = 2000
}

variable "api_cpu_millicores" {
  description = "CPU limit for main API (millicores)"
  type        = number
  default     = 1000
}

variable "frontend_memory_mb" {
  description = "Memory limit for portal frontends (MB)"
  type        = number
  default     = 256
}

variable "frontend_cpu_millicores" {
  description = "CPU limit for portal frontends (millicores)"
  type        = number
  default     = 100
}

variable "aws_credentials_host_path" {
  description = "Path to AWS credentials directory on the k3s node (mounted into pods)"
  type        = string
  default     = "/root/.aws"
}

variable "domain" {
  description = "Primary domain for the cluster (Tailscale MagicDNS or custom domain)"
  type        = string
  default     = ""
}

variable "cloudflare_api_token" {
  description = "Scoped Cloudflare API token (Zone:DNS:Edit, Tunnel:Edit, Access:Edit)"
  type        = string
  sensitive   = true
}

variable "cloudflare_account_id" {
  description = "Cloudflare account ID"
  type        = string
}

variable "cloudflare_tunnel_name" {
  description = "Name for the Cloudflare Tunnel"
  type        = string
  default     = "if-tunnel"
}

variable "cloudflare_team_name" {
  description = "Cloudflare Access team name (<team>.cloudflareaccess.com)"
  type        = string
}

variable "cloudflare_zone_plan" {
  description = "Cloudflare zone plan for managed zones (free, pro, business)"
  type        = string
  default     = "free"
}


variable "gateway_name" {
  description = "Name of the manually-managed Gateway resource"
  type        = string
  default     = "nginx-gateway"
}

variable "gateway_namespace" {
  description = "Namespace of the manually-managed Gateway resource"
  type        = string
  default     = "default"
}

variable "tinyauth_secret" {
  description = "Tinyauth session secret (min 32 chars)"
  type        = string
  sensitive   = true
}

variable "google_oauth_client_id" {
  description = "Google OAuth client ID from Google Cloud Console"
  type        = string
  sensitive   = true
}

variable "google_oauth_client_secret" {
  description = "Google OAuth client secret from Google Cloud Console"
  type        = string
  sensitive   = true
}

variable "tools_path" {
  description = "Path to external tools directory (mounted volume)"
  type        = string
  default     = "/app/tools"
}

variable "specialists_path" {
  description = "Path to specialists directory (mounted volume)"
  type        = string
  default     = "/app/specialists"
}

variable "models_path" {
  description = "Path to models directory (mounted volume)"
  type        = string
  default     = "/app/models"
}

variable "tools_host_path" {
  description = "Host path to tools directory for hostPath volume"
  type        = string
}

variable "specialists_host_path" {
  description = "Host path to specialists directory for hostPath volume"
  type        = string
}

variable "models_host_path" {
  description = "Host path to models directory for hostPath volume"
  type        = string
}

variable "scripts_host_path" {
  description = "Host path to scripts directory for hostPath volume"
  type        = string
}

variable "scripts_path" {
  description = "Path to scripts directory (mounted volume)"
  type        = string
  default     = "/app/scripts"
}

variable "skills_host_path" {
  description = "Host path to AgentSkills directory for hostPath volume"
  type        = string
}

variable "skills_path" {
  description = "Path to AgentSkills directory (mounted volume)"
  type        = string
  default     = "/app/skills"
}

variable "tinyauth_oauth_whitelist" {
  description = "Comma-separated list of allowed Google email addresses"
  type        = string
  default     = ""
}

variable "tinyauth_local_users" {
  description = "Local users in format 'username:bcrypt_hash' (comma-separated for multiple)"
  type        = string
  default     = ""
}

variable "tinyauth_image_tag" {
  description = "Tinyauth container image tag"
  type        = string
  default     = "v5"
}

variable "loki_storage_gb" {
  description = "Storage size for Loki log data (GB)"
  type        = number
  default     = 10
}

variable "prometheus_storage_gb" {
  description = "Storage size for Prometheus metrics (GB)"
  type        = number
  default     = 10
}

variable "grafana_storage_gb" {
  description = "Storage size for Grafana dashboards (GB)"
  type        = number
  default     = 2
}

variable "log_retention_days" {
  description = "Days to retain logs in Loki"
  type        = number
  default     = 7
}

variable "metrics_retention_days" {
  description = "Days to retain metrics in Prometheus"
  type        = number
  default     = 15
}

variable "grafana_admin_password" {
  description = "Grafana admin user password"
  type        = string
  sensitive   = true
  default     = "admin"
}

variable "discord_client_id" {
  description = "Discord Client ID for Powerlifting app"
  type        = string
}

variable "discord_client_secret" {
  description = "Discord Client Secret for Powerlifting app"
  type        = string
  sensitive   = true
}

variable "discord_redirect_uri" {
  description = "Discord Redirect URI for Powerlifting app"
  type        = string
}

variable "jwt_secret" {
  description = "JWT Secret for Powerlifting app"
  type        = string
  sensitive   = true
}

variable "cookie_domain" {
  description = "Cookie domain for Powerlifting app"
  type        = string
  default     = ""
}

variable "cookie_secure" {
  description = "Whether cookie is secure for Powerlifting app"
  type        = string
  default     = "true"
}
