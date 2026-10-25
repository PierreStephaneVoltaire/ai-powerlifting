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

source "docker" "powerlifting_analytics" {
  image    = "public.ecr.aws/docker/library/node:24-bookworm-slim"
  commit   = true
  platform = "linux/amd64"
  changes = [
    "WORKDIR /opt/powerlifting/backend",
    "USER node",
    "CMD [\"node\", \"dist/analyticsSidecar.js\"]"
  ]
}

build {
  name    = "powerlifting-analytics"
  sources = ["source.docker.powerlifting_analytics"]

  provisioner "shell" {
    inline = ["mkdir -p /opt/powerlifting/backend /opt/powerlifting/frontend /opt/powerlifting/packages /opt/powerlifting/services"]
  }

  provisioner "file" {
    sources     = ["../package.json", "../package-lock.json", "../tsconfig.json"]
    destination = "/opt/powerlifting/"
  }

  provisioner "file" {
    sources     = ["../backend/package.json", "../backend/tsconfig.json", "../backend/src"]
    destination = "/opt/powerlifting/backend/"
  }

  provisioner "file" {
    source      = "../frontend/package.json"
    destination = "/opt/powerlifting/frontend/package.json"
  }

  provisioner "file" {
    source      = "../packages/types"
    destination = "/opt/powerlifting/packages/"
  }

  provisioner "file" {
    sources     = ["../services/operations", "../services/calculation_constants.json"]
    destination = "/opt/powerlifting/services/"
  }

  provisioner "shell" {
    inline = [
      "cd /opt/powerlifting",
      "npm ci --workspace=backend --workspace=packages/types",
      "npm run build --workspace=backend",
      "npm prune --omit=dev --workspace=backend --workspace=packages/types",
      "rm -rf /opt/powerlifting/backend/src /opt/powerlifting/frontend /root/.npm",
      "chown -R node:node /opt/powerlifting"
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
