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

variable "opencode_version" {
  type    = string
  default = "1.14.48"
}

source "docker" "if_agent" {
  image    = "public.ecr.aws/docker/library/python:3.12-slim"
  commit   = true
  platform = "linux/amd64"
  changes = [
    "WORKDIR /app/src",
    "ENV PATH=/root/.local/bin:/usr/local/bin:$PATH",
    "CMD [\"python\", \"-m\", \"uvicorn\", \"main:app\", \"--host\", \"0.0.0.0\", \"--port\", \"8000\"]"
  ]
}

build {
  name    = "if-agent-api"
  sources = ["source.docker.if_agent"]

  # Install system dependencies 
  provisioner "shell" {
    inline = [
      "export DEBIAN_FRONTEND=noninteractive && apt-get update && apt-get install -y curl unzip ca-certificates git iputils-ping dnsutils netcat-openbsd iproute2 procps default-jre-headless nodejs npm",
      "rm -rf /var/lib/apt/lists/*",
      "mkdir -p /app/src"
    ]
  }
provisioner "shell" {
    inline = [
      "export DEBIAN_FRONTEND=noninteractive",
      "apt-get update",
      "apt-get upgrade -y perl libhttp-daemon-perl libexpat1 curl libxml2",
      "apt-get install -y libexpat1-dev || true",
      "rm -rf /var/lib/apt/lists/*"
    ]
  }

  # Install OpenCode runtime used by planner/domain/technical subprocess runs.
  provisioner "shell" {
    inline = [
      "npm install -g opencode-ai@${var.opencode_version}",
      "opencode --version"
    ]
  }

  # Install uv for fast Python package management
  provisioner "shell" {
    inline = [
      "curl -LsSf https://astral.sh/uv/install.sh | sh",
      "export PATH=\"/root/.local/bin:$PATH\"",
      "uv --version"
    ]
  }

  # Copy requirements first for better caching
  provisioner "file" {
    source      = "../app/requirements.txt"
    destination = "/app/requirements.txt"
  }

  # Install torch CPU wheel first (scoped index to avoid polluting other package lookups)
  provisioner "shell" {
    inline = [
      "export PATH=\"/root/.local/bin:$PATH\"",
      "uv pip install --system torch --extra-index-url https://download.pytorch.org/whl/cpu"
    ]
  }

  # Install remaining Python dependencies using PyPI only
  provisioner "shell" {
    inline = [
      "export PATH=\"/root/.local/bin:$PATH\"",
      "cd /app && uv pip install --system -r requirements.txt"
    ]
  }

  # Copy source code — Packer uploads the directory itself into /app/,
  # producing /app/src/ with all contents (data/, sandbox/, logs/, etc.)
  provisioner "file" {
    source      = "../app/src"
    destination = "/app/"
  }

  # Copy specialists (source of truth at project root) into expected runtime location
  provisioner "file" {
    source      = "../specialists"
    destination = "/app/src/agent/prompts/"
  }

  # Copy external tool plugins into expected runtime location
  provisioner "file" {
    source      = "../tools"
    destination = "/app/"
  }

  # Copy main system prompt to /app/ (code resolves via Path(__file__).parent…parent…parent)
  provisioner "file" {
    source      = "../app/main_system_prompt.txt"
    destination = "/app/main_system_prompt.txt"
  }

  # Ensure writable directories exist inside /app/src (match local dev layout)
  provisioner "shell" {
    inline = [
      "mkdir -p /app/src/data/memory_db",
      "mkdir -p /app/src/data/conversations",
      "mkdir -p /app/src/data/facts",
      "mkdir -p /app/src/logs"
    ]
  }

  # Clean up unnecessary files
  provisioner "shell" {
    inline = [
      "rm -rf /app/src/data/memory.json",
      "rm -rf /root/.cache"
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
