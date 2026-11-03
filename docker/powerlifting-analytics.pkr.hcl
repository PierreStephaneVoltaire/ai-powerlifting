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
    "WORKDIR /opt/powerlifting/src/backend",
    "USER node",
    "CMD [\"node\", \"dist/analyticsSidecar.js\"]"
  ]
}

build {
  name    = "powerlifting-analytics"
  sources = ["source.docker.powerlifting_analytics"]

  provisioner "shell" {
    inline = ["mkdir -p /opt/powerlifting/src/backend /opt/powerlifting/src/frontend /opt/powerlifting/src/dependencies /opt/powerlifting/src/services"]
  }

  provisioner "file" {
    sources     = ["../package.json", "../package-lock.json", "../tsconfig.json"]
    destination = "/opt/powerlifting/"
  }

  provisioner "file" {
    sources     = ["../src/backend/package.json", "../src/backend/tsconfig.json", "../src/backend/src"]
    destination = "/opt/powerlifting/src/backend/"
  }

  provisioner "file" {
    source      = "../src/frontend/package.json"
    destination = "/opt/powerlifting/src/frontend/package.json"
  }

  provisioner "file" {
    source      = "../src/dependencies/types"
    destination = "/opt/powerlifting/src/dependencies/"
  }

  provisioner "file" {
    sources     = ["../src/services/operations", "../src/services/calculation_constants.json"]
    destination = "/opt/powerlifting/src/services/"
  }

  provisioner "shell" {
    inline = [
      "cd /opt/powerlifting",
      "npm ci --workspace=src/backend --workspace=src/dependencies/types",
      "npm run build --workspace=src/backend",
      "npm prune --omit=dev --workspace=src/backend --workspace=src/dependencies/types",
      "rm -rf /opt/powerlifting/src/backend/src /opt/powerlifting/src/frontend /root/.npm",
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
