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

source "docker" "powerlifting_analytics_export" {
  image       = "cgr.dev/chainguard/wolfi-base:latest"
  commit      = true
  run_command = ["-d", "-i", "-t", "--entrypoint=/bin/sh", "--", "{{.Image}}"]
  platform    = "linux/amd64"
  changes = [
    "USER 65532:65532",
    "EXPOSE 8000 50051",
    "ENTRYPOINT [\"/pl-analytics-export\"]"
  ]
}

build {
  name    = "powerlifting-analytics-export"
  sources = ["source.docker.powerlifting_analytics_export"]

  provisioner "shell" {
    inline = ["apk add --no-cache tzdata"]
  }

  provisioner "shell-local" {
    inline = [
      "rm -rf .build/analytics-export && mkdir -p .build/analytics-export",
      "docker run --rm --platform linux/amd64 --user $(id -u):$(id -g) -e HOME=/tmp -e GOCACHE=/tmp/gocache -e GOPATH=/tmp/go -e CGO_ENABLED=0 -e GOOS=linux -e GOARCH=amd64 -v \"$(cd .. && pwd)/src/services:/workspace/services:ro\" -v \"$(pwd)/.build/analytics-export:/out\" -w /workspace/services/analytics-export cgr.dev/chainguard/go:latest build -trimpath -ldflags '-s -w' -o /out/pl-analytics-export ."
    ]
  }

  provisioner "file" {
    generated   = true
    source      = ".build/analytics-export/pl-analytics-export"
    destination = "/pl-analytics-export"
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
