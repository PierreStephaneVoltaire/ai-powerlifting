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

variable "portal_port" {
  type    = string
  default = "3000"
}

source "docker" "portal_backend" {
  image    = "public.ecr.aws/docker/library/node:20-alpine"
  commit   = true
  platform = "linux/amd64"
  changes = [
    "WORKDIR /workspace/backend",
    "ENV NODE_ENV=production",
    "EXPOSE ${var.portal_port}",
    "CMD [\"node\", \"dist/server.js\"]"
  ]
}

build {
  name    = "portal-backend"
  sources = ["source.docker.portal_backend"]

  # Install build tools
  provisioner "shell" {
    inline = [
      "apk add --no-cache curl",
      "mkdir -p /workspace"
    ]
  }

  # Copy entire portal workspace (needed for npm workspaces + shared types package)
  provisioner "file" {
    source      = "../utils/${var.portal_name}/"
    destination = "/workspace"
  }

  # Install all workspace dependencies and build optional shared types, then backend
  # Supports npm workspace portals with or without packages/types, plus standalone backends
  provisioner "shell" {
    inline = [
      "if [ -f /workspace/package.json ] && grep -q '\"workspaces\"' /workspace/package.json; then cd /workspace && npm install && if [ -f /workspace/packages/types/package.json ]; then npm run build --workspace=packages/types; fi && npm run build --workspace=backend; else cd /workspace/backend && npm install && npm run build; fi"
    ]
  }

  # Create non-root user
  provisioner "shell" {
    inline = [
      "addgroup -g 1001 -S nodejs",
      "adduser -S nodejs -u 1001 -G nodejs",
      "chown -R nodejs:nodejs /workspace/backend"
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
