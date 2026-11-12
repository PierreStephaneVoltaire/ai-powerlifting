locals {
  enrollment_fields = {
    username        = { label = "Username", type = "username", order = 0 }
    name            = { label = "Name", type = "text", order = 1 }
    email           = { label = "Email", type = "email", order = 2 }
    password        = { label = "Password", type = "password", order = 3 }
    password_repeat = { label = "Password (repeat)", type = "password", order = 4 }
  }
}

resource "authentik_stage_prompt_field" "enrollment" {
  for_each    = local.enrollment_fields
  name        = "nolift-enrollment-${each.key}"
  field_key   = each.key
  label       = each.value.label
  type        = each.value.type
  placeholder = each.value.label
  required    = true
  order       = each.value.order
}

resource "authentik_stage_prompt" "enrollment" {
  name   = "nolift-enrollment-prompt"
  fields = [for key in keys(local.enrollment_fields) : authentik_stage_prompt_field.enrollment[key].id]
}

resource "authentik_stage_user_write" "enrollment" {
  name                     = "nolift-enrollment-write"
  create_users_as_inactive = false
  user_creation_mode       = "always_create"
}

resource "authentik_stage_user_login" "enrollment" {
  name = "nolift-enrollment-login"
}

resource "authentik_flow" "enrollment" {
  name           = "nolift-enrollment"
  title          = "Sign up for NoLift"
  slug           = "nolift-enrollment"
  designation    = "enrollment"
  authentication = "require_unauthenticated"
}

resource "authentik_flow_stage_binding" "enrollment" {
  for_each = {
    10 = authentik_stage_prompt.enrollment.id
    20 = authentik_stage_user_write.enrollment.id
    30 = authentik_stage_user_login.enrollment.id
  }
  target = authentik_flow.enrollment.uuid
  stage  = each.value
  order  = tonumber(each.key)
}
