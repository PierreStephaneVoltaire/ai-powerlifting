variable "litellm_mcp_servers" {
  type = map(object({
    url           = string
    extra_headers = optional(list(string), ["authorization"])
  }))
  default = {}
}

variable "litellm_virtual_key_assistant" {
  type      = string
  default   = ""
  sensitive = true
}

variable "litellm_virtual_key_coach" {
  type      = string
  default   = ""
  sensitive = true
}

locals {
  litellm_mcp_servers = {
    for alias, server in var.litellm_mcp_servers : alias => {
      url           = server.url
      transport     = "http"
      auth_type     = "none"
      extra_headers = server.extra_headers
    }
  }

  litellm_virtual_keys = {
    for consumer, key in {
      assistant = var.litellm_virtual_key_assistant
      coach     = var.litellm_virtual_key_coach
    } : consumer => key if nonsensitive(key != "")
  }
}

resource "kubernetes_secret_v1" "litellm_virtual_key" {
  for_each = local.litellm_virtual_keys

  metadata {
    name      = "litellm-virtual-key-${each.key}"
    namespace = var.namespace
  }

  data = {
    LITELLM_API_KEY = each.value
  }
}
