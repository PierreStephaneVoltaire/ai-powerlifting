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

source "docker" "powerlifting_profile" {
  image       = "cgr.dev/chainguard/wolfi-base:latest"
  commit      = true
  run_command = ["-d", "-i", "-t", "--entrypoint=/bin/sh", "--", "{{.Image}}"]
  platform    = "linux/amd64"
  changes = [
    "USER 65532:65532",
    "EXPOSE 8000",
    "ENTRYPOINT [\"/pl-profile\"]"
  ]
}

build {
  name    = "powerlifting-profile"
  sources = ["source.docker.powerlifting_profile"]

  provisioner "shell" {
    inline = ["apk add --no-cache tzdata"]
  }

  provisioner "shell-local" {
    inline = [
      "rm -rf .build/profile && mkdir -p .build/profile",
      "docker run --rm --platform linux/amd64 --user $(id -u):$(id -g) -e HOME=/tmp -e GOCACHE=/tmp/gocache -e GOPATH=/tmp/go -e CGO_ENABLED=0 -e GOOS=linux -e GOARCH=amd64 -v \"$(cd .. && pwd)/src/services:/workspace/services:ro\" -v \"$(pwd)/.build/profile:/out\" -w /workspace/services/profile cgr.dev/chainguard/go:latest build -trimpath -ldflags '-s -w' -o /out/pl-profile ."
    ]
  }

  provisioner "file" {
    generated   = true
    source      = ".build/profile/pl-profile"
    destination = "/pl-profile"
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
