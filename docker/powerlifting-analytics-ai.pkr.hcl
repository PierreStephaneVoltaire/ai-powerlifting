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

source "docker" "powerlifting_analytics_ai" {
  image    = "gcr.io/distroless/static-debian12:debug-nonroot"
  commit   = true
  platform = "linux/amd64"
  changes = [
    "USER nonroot",
    "EXPOSE 8000 50051",
    "ENTRYPOINT [\"/pl-analytics-ai\"]"
  ]
}

build {
  name    = "powerlifting-analytics-ai"
  sources = ["source.docker.powerlifting_analytics_ai"]

  provisioner "shell-local" {
    inline = [
      "rm -rf .build/analytics-ai && mkdir -p .build/analytics-ai",
      "docker run --rm --platform linux/amd64 --user $(id -u):$(id -g) -e HOME=/tmp -e GOCACHE=/tmp/gocache -e GOPATH=/tmp/go -e CGO_ENABLED=0 -e GOOS=linux -e GOARCH=amd64 -v \"$(cd .. && pwd)/src/services:/workspace/services:ro\" -v \"$(pwd)/.build/analytics-ai:/out\" -w /workspace/services/analytics-ai public.ecr.aws/docker/library/golang:1-bookworm go build -trimpath -ldflags '-s -w' -o /out/pl-analytics-ai ."
    ]
  }

  provisioner "file" {
    source      = ".build/analytics-ai/pl-analytics-ai"
    destination = "/pl-analytics-ai"
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
