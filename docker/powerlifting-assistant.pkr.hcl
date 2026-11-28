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

source "docker" "powerlifting_assistant" {
  image       = "cgr.dev/chainguard/wolfi-base:latest"
  commit      = true
  run_command = ["-d", "-i", "-t", "--entrypoint=/bin/sh", "--", "{{.Image}}"]
  platform    = "linux/amd64"
  changes = [
    "USER 65532:65532",
    "EXPOSE 8000",
    "ENTRYPOINT [\"/pl-assistant\"]"
  ]
}

build {
  name    = "powerlifting-assistant"
  sources = ["source.docker.powerlifting_assistant"]

  provisioner "shell" {
    inline = ["apk add --no-cache tzdata", "mkdir -p /operations"]
  }

  provisioner "shell-local" {
    inline = [
      "rm -rf .build/assistant && mkdir -p .build/assistant",
      "docker run --rm --platform linux/amd64 --user $(id -u):$(id -g) -e HOME=/tmp -e GOCACHE=/tmp/gocache -e GOPATH=/tmp/go -e CGO_ENABLED=0 -e GOOS=linux -e GOARCH=amd64 -v \"$(cd .. && pwd)/src/services:/workspace/services:ro\" -v \"$(pwd)/.build/assistant:/out\" -w /workspace/services/assistant cgr.dev/chainguard/go:latest build -trimpath -ldflags '-s -w' -o /out/pl-assistant ./cmd/assistant"
    ]
  }

  provisioner "file" {
    generated   = true
    source      = ".build/assistant/pl-assistant"
    destination = "/pl-assistant"
  }

  provisioner "file" {
    source      = "../src/services/operations/"
    destination = "/operations/"
  }

  provisioner "file" {
    source      = "../src/services/runtime/permissions.json"
    destination = "/permissions.json"
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
