packer {
  required_plugins {
    docker = {
      version = ">= 1.0.0"
      source  = "github.com/hashicorp/docker"
    }
  }
}

# One self-contained container image per powerlifting tool, used with the
# Fission `container` executor (not newdeploy). The container executor runs
# the image directly as the function pod — no Environment, no Package, no
# fetcher, no specialize step. The image itself serves HTTP on :8888.
#
# Image layout:
#   /app/server.py       <- Flask server (from lambda/fission_server.py)
#   /app/main.py         <- fission_entry.py (entry, not used at runtime)
#   /app/tool_id.txt     <- "<tool_id>"
#   /app/<tool_id>/      <- handler.py, core.py, __init__.py
#   /app/program_store.py <- layer modules at app root
#   /app/boto3/ ...      <- pip-installed deps at /app root
# The Flask server imports <tool_id>.handler and calls handler(event, context)
# on each POST, returning the JSON result. PYTHONPATH=/app makes all deps importable.

variable "image_repository" {
  type = string
}

variable "image_tag" {
  type = string
}

variable "tool_id" {
  type = string
}

variable "source_archive" {
  type = string
}

variable "tag_latest" {
  type    = bool
  default = false
}

variable "image_tag_sha" {
  type    = string
  default = ""
}

source "docker" "pl_fn" {
  image    = "public.ecr.aws/docker/library/python:3.13-slim"
  commit   = true
  platform = "linux/amd64"
  changes = [
    "ENV PATH=/usr/local/bin:/usr/bin:/bin",
    "ENV PYTHONDONTWRITEBYTECODE=1",
    "ENV PYTHONUNBUFFERED=1",
    "ENV PYTHONPATH=/app",
    "EXPOSE 8888",
    "CMD [\"python\", \"/app/server.py\"]"
  ]
}

build {
  name    = "pl-fn"
  sources = ["source.docker.pl_fn"]

  provisioner "shell" {
    inline = [
      "apt-get update -qq && apt-get install -y -qq unzip ca-certificates >/dev/null 2>&1",
      "rm -rf /var/lib/apt/lists/*",
      "pip install --no-cache-dir flask gunicorn",
      "mkdir -p /app"
    ]
  }

  provisioner "file" {
    source      = var.source_archive
    destination = "/tmp/src.zip"
  }

  provisioner "shell" {
    inline = [
      "cd /app",
      "unzip -q -o /tmp/src.zip",
      "if [ -f requirements.txt ]; then pip install --no-cache-dir --target=/app -r requirements.txt; fi",
      "rm -f /tmp/src.zip",
      "test -f /app/main.py",
      "echo '${var.tool_id}' > /app/tool_id.txt"
    ]
  }

  provisioner "file" {
    source      = "../lambda/fission_server.py"
    destination = "/app/server.py"
  }

  post-processors {
    post-processor "docker-tag" {
      repository = var.image_repository
      tags = var.image_tag_sha != "" ? (
        var.tag_latest ? [var.image_tag, var.image_tag_sha, "latest"] : [var.image_tag, var.image_tag_sha]
      ) : (
        var.tag_latest ? [var.image_tag, "latest"] : [var.image_tag]
      )
    }
    post-processor "docker-push" {
      ecr_login    = true
      login_server = split("/", var.image_repository)[0]
    }
  }
}
