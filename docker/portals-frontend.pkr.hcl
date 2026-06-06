packer {
  required_plugins {
    docker = {
      version = ">= 1.0.0"
      source  = "github.com/hashicorp/docker"
    }
  }
}

variable "image_repository" {
  type = string
}

variable "image_tag" {
  type    = string
  default = "latest"
}

variable "tag_latest" {
  type    = bool
  default = true
}

variable "portal_name" {
  type    = string
  default = "portal"
}

variable "api_url" {
  type    = string
  default = ""
}

source "docker" "portal_frontend" {
  image    = "public.ecr.aws/docker/library/node:20-alpine"
  commit   = true
  platform = "linux/amd64"
  changes = [
    "WORKDIR /app",
    "EXPOSE 3001",
    "CMD [\"serve\", \"-s\", \"/app/dist\", \"-l\", \"3001\"]"
  ]
}

build {
  name    = "portal-frontend"
  sources = ["source.docker.portal_frontend"]

  # Install build tools
  provisioner "shell" {
    inline = [
      "apk add --no-cache curl",
      "mkdir -p /workspace /app"
    ]
  }

  # Copy entire portal workspace (needed for npm workspaces + shared types package)
  provisioner "file" {
    source      = "../utils/${var.portal_name}/"
    destination = "/workspace"
  }

  # Install all workspace dependencies, build optional shared types, then build frontend
  # Supports npm workspace portals with or without packages/types, plus standalone frontends
  # Sets both VITE_API_URL and VITE_API_BASE_URL since different portals use different var names
  provisioner "shell" {
    inline = [
      "if [ -f /workspace/package.json ] && grep -q '\"workspaces\"' /workspace/package.json; then cd /workspace && npm install && if [ -f /workspace/packages/types/package.json ]; then npm run build --workspace=packages/types; fi && VITE_API_URL=${var.api_url} VITE_API_BASE_URL=${var.api_url} npm run build --workspace=frontend && cp -r /workspace/frontend/dist /app/dist; else cd /workspace/frontend && npm install && VITE_API_URL=${var.api_url} VITE_API_BASE_URL=${var.api_url} npm run build && cp -r /workspace/frontend/dist /app/dist; fi",
      "npm install -g serve"
    ]
  }

  post-processors {
    post-processor "docker-tag" {
      repository = var.image_repository
      tags       = var.tag_latest ? [var.image_tag, "latest"] : [var.image_tag]
    }
    post-processor "docker-push" {
      ecr_login    = true
      login_server = split("/", var.image_repository)[0]
    }
  }
}
