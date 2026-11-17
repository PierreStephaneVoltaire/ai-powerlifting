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

source "docker" "powerlifting_weight_log" {
  image       = "gcr.io/distroless/static-debian12:debug-nonroot"
  commit      = true
  run_command = ["-d", "-i", "-t", "--entrypoint=/busybox/sh", "--", "{{.Image}}"]
  platform    = "linux/amd64"
  changes = [
    "USER nonroot",
    "EXPOSE 8000",
    "ENTRYPOINT [\"/pl-weight-log\"]"
  ]
}

build {
  name    = "powerlifting-weight-log"
  sources = ["source.docker.powerlifting_weight_log"]

  provisioner "shell-local" {
    inline = [
      "rm -rf .build/weight-log && mkdir -p .build/weight-log",
      "docker run --rm --platform linux/amd64 --user $(id -u):$(id -g) -e HOME=/tmp -e GOCACHE=/tmp/gocache -e GOPATH=/tmp/go -e CGO_ENABLED=0 -e GOOS=linux -e GOARCH=amd64 -v \"$(cd .. && pwd)/src/services:/workspace/services:ro\" -v \"$(pwd)/.build/weight-log:/out\" -w /workspace/services/weight_log public.ecr.aws/docker/library/golang:1-bookworm go build -trimpath -ldflags '-s -w' -o /out/pl-weight-log ."
    ]
  }

  provisioner "file" {
    generated   = true
    source      = ".build/weight-log/pl-weight-log"
    destination = "/pl-weight-log"
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
