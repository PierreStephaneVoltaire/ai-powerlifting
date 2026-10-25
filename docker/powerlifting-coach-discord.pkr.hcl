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

source "docker" "powerlifting_coach_discord" {
  image    = "public.ecr.aws/docker/library/python:3.12-slim"
  commit   = true
  platform = "linux/amd64"
  changes = [
    "WORKDIR /opt/powerlifting",
    "ENV PYTHONUNBUFFERED=1",
    "USER relay",
    "EXPOSE 8000",
    "CMD [\"python\", \"-m\", \"uvicorn\", \"services.coach_discord.app:main\", \"--factory\", \"--host\", \"0.0.0.0\", \"--port\", \"8000\"]"
  ]
}

build {
  name    = "powerlifting-coach-discord"
  sources = ["source.docker.powerlifting_coach_discord"]

  provisioner "shell" {
    inline = ["mkdir -p /opt/powerlifting/services"]
  }

  provisioner "file" {
    sources     = ["../services/__init__.py", "../services/coach_discord"]
    destination = "/opt/powerlifting/services/"
  }

  provisioner "shell" {
    inline = [
      "pip install --no-cache-dir -r /opt/powerlifting/services/coach_discord/requirements.txt",
      "find /opt/powerlifting -name __pycache__ -type d -prune -exec rm -rf {} +",
      "useradd -m -u 10001 relay"
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
