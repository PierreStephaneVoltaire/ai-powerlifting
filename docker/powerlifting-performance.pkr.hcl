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

source "docker" "powerlifting_performance" {
  image       = "gcr.io/distroless/static-debian12:debug-nonroot"
  commit      = true
  run_command = ["-d", "-i", "-t", "--entrypoint=/busybox/sh", "--", "{{.Image}}"]
  platform    = "linux/amd64"
  changes = [
    "USER nonroot",
    "EXPOSE 8000",
    "ENTRYPOINT [\"/pl-performance\"]"
  ]
}

build {
  name    = "powerlifting-performance"
  sources = ["source.docker.powerlifting_performance"]

  provisioner "shell-local" {
    inline = [
      "rm -rf .build/performance && mkdir -p .build/performance",
      "docker run --rm --platform linux/amd64 --user $(id -u):$(id -g) -e HOME=/tmp -e GOCACHE=/tmp/gocache -e GOPATH=/tmp/go -e CGO_ENABLED=0 -e GOOS=linux -e GOARCH=amd64 -v \"$(cd .. && pwd)/src/services:/workspace/services:ro\" -v \"$(pwd)/.build/performance:/out\" -w /workspace/services/performance public.ecr.aws/docker/library/golang:1-bookworm go build -trimpath -ldflags '-s -w' -o /out/pl-performance ."
    ]
  }

  provisioner "file" {
    generated   = true
    source      = ".build/performance/pl-performance"
    destination = "/pl-performance"
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
