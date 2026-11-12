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

source "docker" "powerlifting_rankings" {
  image    = "public.ecr.aws/docker/library/debian:bookworm-slim"
  commit   = true
  platform = "linux/amd64"
  changes = [
    "USER 10001",
    "EXPOSE 8000",
    "ENTRYPOINT [\"/usr/local/bin/pl-rankings\"]"
  ]
}

build {
  name    = "powerlifting-rankings"
  sources = ["source.docker.powerlifting_rankings"]

  provisioner "shell-local" {
    inline = [
      "rm -rf .build/rankings && mkdir -p .build/rankings",
      "docker run --rm --platform linux/amd64 --user $(id -u):$(id -g) -e HOME=/tmp -e CARGO_HOME=/tmp/cargo -e CARGO_TARGET_DIR=/tmp/target -e CARGO_BUILD_JOBS=4 -v \"$(cd .. && pwd)/src/services:/workspace/services:ro\" -v \"$(pwd)/.build/rankings:/out\" -w /workspace/services/rankings public.ecr.aws/docker/library/rust:1-slim-bookworm sh -c 'cargo build --release --locked && cp /tmp/target/release/pl-rankings /out/pl-rankings'"
    ]
  }

  provisioner "shell" {
    inline = [
      "apt-get update",
      "apt-get install -y --no-install-recommends ca-certificates",
      "rm -rf /var/lib/apt/lists/*",
      "useradd --no-create-home --uid 10001 service"
    ]
  }

  provisioner "file" {
    source      = ".build/rankings/pl-rankings"
    destination = "/usr/local/bin/pl-rankings"
  }

  provisioner "shell" {
    inline = ["chmod 755 /usr/local/bin/pl-rankings"]
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
