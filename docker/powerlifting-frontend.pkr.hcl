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

variable "api_url" {
  type    = string
  default = "/api"
}

source "docker" "powerlifting_frontend" {
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
  name    = "powerlifting-frontend"
  sources = ["source.docker.powerlifting_frontend"]

  provisioner "shell" {
    inline = [
      "apk add --no-cache curl",
      "mkdir -p /workspace /app"
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
      "  VITE_API_URL=${var.api_url} VITE_API_BASE_URL=${var.api_url} npm run build --workspace=frontend",
      "  cp -r frontend/dist /app/dist",
      "else",
      "  cd frontend && npm ci || npm install && VITE_API_URL=${var.api_url} VITE_API_BASE_URL=${var.api_url} npm run build && cp -r dist /app/dist",
      "fi",
      "npm install -g serve"
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
