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

source "docker" "powerlifting_backend" {
  image    = "public.ecr.aws/docker/library/node:20-alpine"
  commit   = true
  platform = "linux/amd64"
  changes = [
    "WORKDIR /workspace/backend",
    "ENV NODE_ENV=production",
    "EXPOSE 3005",
    "CMD [\"node\", \"dist/server.js\"]"
  ]
}

build {
  name    = "powerlifting-backend"
  sources = ["source.docker.powerlifting_backend"]

  provisioner "shell" {
    inline = [
      "apk add --no-cache curl",
      "mkdir -p /workspace"
    ]
  }

  provisioner "file" {
    source      = "../"
    destination = "/workspace"
  }

  provisioner "shell" {
    inline = [
      "cd /workspace",
      "if [ -f package.json ] && grep -q '\"workspaces\"' package.json; then",
      "  npm ci || npm install",
      "  if [ -f packages/types/package.json ]; then npm run build --workspace=packages/types || true; fi",
      "  npm run build --workspace=backend",
      "else",
      "  cd backend && npm ci || npm install && npm run build",
      "fi"
    ]
  }

  provisioner "shell" {
    inline = [
      "addgroup -g 1001 -S nodejs || true",
      "adduser -S nodejs -u 1001 -G nodejs 2>/dev/null || true",
      "chown -R nodejs:nodejs /workspace/backend || true"
    ]
  }

  post-processors {
    post-processor "docker-tag" {
      repository = var.image_repository
      tags       = [var.image_tag, "latest"]
    }
    post-processor "docker-push" {
      ecr_login    = true
      login_server = split("/", var.image_repository)[0]
    }
  }
}
