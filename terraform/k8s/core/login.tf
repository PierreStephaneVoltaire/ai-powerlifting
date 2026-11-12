resource "authentik_stage_identification" "default_authentication" {
  name                      = "default-authentication-identification"
  user_fields               = ["email", "username"]
  sources                   = [authentik_source_oauth.discord.uuid]
  show_source_labels        = true
  case_insensitive_matching = true
  enrollment_flow           = authentik_flow.enrollment.uuid
}
