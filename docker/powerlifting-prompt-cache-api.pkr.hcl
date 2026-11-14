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

source "docker" "powerlifting_prompt_cache_api" {
  image       = "gcr.io/distroless/static-debian12:debug-nonroot"
  commit      = true
  run_command = ["-d", "-i", "-t", "--entrypoint=/busybox/sh", "--", "{{.Image}}"]
  platform    = "linux/amd64"
  changes = [
    "USER nonroot",
    "EXPOSE 8000",
    "ENTRYPOINT [\"/pl-prompt-cache-api\"]"
  ]
}

build {
  name    = "powerlifting-prompt-cache-api"
  sources = ["source.docker.powerlifting_prompt_cache_api"]

  provisioner "shell-local" {
    inline = [
      "rm -rf .build/prompt-cache-api && mkdir -p .build/prompt-cache-api",
      "docker run --rm --platform linux/amd64 --user $(id -u):$(id -g) -e HOME=/tmp -e GOCACHE=/tmp/gocache -e GOPATH=/tmp/go -e CGO_ENABLED=0 -e GOOS=linux -e GOARCH=amd64 -v \"$(cd .. && pwd)/src/services:/workspace/services:ro\" -v \"$(pwd)/.build/prompt-cache-api:/out\" -w /workspace/services/prompt-cache public.ecr.aws/docker/library/golang:1-bookworm go build -trimpath -ldflags '-s -w' -o /out/pl-prompt-cache-api ."
    ]
  }

  provisioner "file" {
    generated   = true
    source      = ".build/prompt-cache-api/pl-prompt-cache-api"
    destination = "/pl-prompt-cache-api"
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
