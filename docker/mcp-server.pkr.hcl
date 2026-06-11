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

variable "tag_latest" {
  type    = bool
  default = true
}

source "docker" "mcp_server" {
  image    = "public.ecr.aws/docker/library/python:3.12-slim"
  commit   = true
  platform = "linux/amd64"
  changes = [
    "WORKDIR /app",
    "ENV PATH=/usr/local/bin:$PATH",
    "ENV PYTHONUNBUFFERED=1",
    "ENV PYTHONDONTWRITEBYTECODE=1",
    "ENV PIP_NO_CACHE_DIR=1",
    "ENV PIP_DISABLE_PIP_VERSION_CHECK=1",
    "EXPOSE 8000",
    "CMD [\"/entrypoint.sh\"]",
  ]
}

build {
  name    = "if-mcp-server"
  sources = ["source.docker.mcp_server"]

  provisioner "shell" {
    inline = [
      "export DEBIAN_FRONTEND=noninteractive",
      "apt-get update",
      "apt-get install -y --no-install-recommends bash curl ca-certificates",
      "rm -rf /var/lib/apt/lists/*",
    ]
  }

  provisioner "shell" {
    inline = [
      "mkdir -p /app/tools",
    ]
  }

  provisioner "file" {
    source      = "../tools/mcp_server.py"
    destination = "/app/tools/mcp_server.py"
  }

  provisioner "file" {
    source      = "../tools/sdk_compat.py"
    destination = "/app/tools/sdk_compat.py"
  }

  provisioner "file" {
    source      = "../app/src"
    destination = "/app/"
  }

  provisioner "file" {
    source      = "mcp-server-entrypoint.sh"
    destination = "/entrypoint.sh"
  }

  provisioner "shell" {
    inline = [
      "python3 -m pip install --no-cache-dir 'mcp[cli]>=1.2.0,<2.0.0' 'uvicorn[standard]>=0.24.0' 'starlette>=0.40.0' 'pydantic>=2.5.0'",
    ]
  }

  provisioner "shell" {
    inline = [
      "chmod +x /entrypoint.sh",
      "mkdir -p /app/src/data /app/src/sandbox",
      "echo 'if-mcp-server' > /app/IMAGE_KIND",
    ]
  }

  post-processors {
    post-processor "docker-tag" {
      repository = var.image_repository
      tags       = var.tag_latest ? [var.image_tag, "latest"] : [var.image_tag]
    }
    post-processor "docker-push" {
      ecr_login    = true
      login_server = split("/", var.image_repository)[0]
    }
  }
}
