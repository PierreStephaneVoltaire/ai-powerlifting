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
    "WORKDIR /workspace/src/backend",
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
      "cd /workspace/src",
      "test -f services/operations/program.json",
      "npm ci",
      "npm run build --workspace=dependencies/types",
      "npm run build --workspace=backend"
    ]
  }

  provisioner "shell" {
    inline = [
      "addgroup -g 1001 -S nodejs || true",
      "adduser -S nodejs -u 1001 -G nodejs 2>/dev/null || true",
      "chown -R nodejs:nodejs /workspace/src/backend || true"
    ]
  }

  post-processors {
    post-processor "docker-tag" {
      repository = var.image_repository
      tags       = [var.image_tag]
    }
    post-processor "docker-push" {
      name         = "publish"
      ecr_login    = true
      login_server = split("/", var.image_repository)[0]
    }
  }
}
