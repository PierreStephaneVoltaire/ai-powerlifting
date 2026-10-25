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

source "docker" "powerlifting_coach_agent" {
  image    = "public.ecr.aws/docker/library/python:3.12-slim"
  commit   = true
  platform = "linux/amd64"
  changes = [
    "WORKDIR /opt/powerlifting",
    "ENV PYTHONUNBUFFERED=1 COACH_STATE_DIR=/var/lib/coach CODEX_HOME=/var/lib/coach/codex HOME=/var/lib/coach",
    "USER coach",
    "EXPOSE 8000",
    "ENTRYPOINT [\"/usr/bin/tini\", \"--\"]",
    "CMD [\"python\", \"-m\", \"uvicorn\", \"services.coach.app:main\", \"--factory\", \"--host\", \"0.0.0.0\", \"--port\", \"8000\"]"
  ]
}

build {
  name    = "powerlifting-coach-agent"
  sources = ["source.docker.powerlifting_coach_agent"]

  provisioner "shell" {
    inline = [
      "apt-get update",
      "apt-get install -y --no-install-recommends ca-certificates git tini",
      "rm -rf /var/lib/apt/lists/*",
      "mkdir -p /opt/powerlifting/services /var/lib/coach/codex"
    ]
  }

  provisioner "file" {
    sources     = ["../services/__init__.py", "../services/permissions.json", "../services/operations", "../services/coach"]
    destination = "/opt/powerlifting/services/"
  }

  provisioner "shell" {
    inline = [
      "pip install --no-cache-dir -r /opt/powerlifting/services/coach/requirements.txt",
      "find /opt/powerlifting -name __pycache__ -type d -prune -exec rm -rf {} +",
      "useradd -m -u 10001 coach",
      "chown -R coach:coach /var/lib/coach"
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
