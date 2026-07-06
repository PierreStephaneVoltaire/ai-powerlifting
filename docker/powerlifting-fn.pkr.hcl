packer {
  required_plugins {
    docker = {
      version = ">= 1.0.0"
      source  = "github.com/hashicorp/docker"
    }
  }
}

# One Fission OCI-package image per powerlifting tool.
#
# Fission's source-package path (source.literal + buildcmd) falls over for the
# scipy/pandas tools: the deploy archive exceeds the fetcher upload body limit
# (HTTP 413 Request Entity Too Large) and the single shared python-builder
# serialises/collides on concurrent builds. Instead we pre-build one OCI image
# per tool and reference it from the Fission Package via
#   spec.deployment.oci.image = "<repo>:<tool_id>-<hash>"
# The Fission fetcher pulls this image and extracts its filesystem to
# /userfunc/deployarchive (the newdeploy runtime loads main.main from there),
# so NO buildmgr / source build / archive upload happens at function-create time.
#
# Image layout (must match what fission_entry.py expects):
#   /userfunc/deployarchive/main.py            <- fission_entry.py (the entry)
#   /userfunc/deployarchive/tool_id.txt        <- "<tool_id>"
#   /userfunc/deployarchive/<tool_id>/         <- handler.py, core.py, __init__.py
#   /userfunc/deployarchive/program_store.py   <- layer modules at archive root
#   /userfunc/deployarchive/scipy/ ...         <- pip-installed deps at archive root
# fission_entry adds /userfunc to sys.path and imports <tool_id>.handler, and
# handler does `from .core import ...` / `from program_store import ...`, so
# having deps + layer modules at the deployarchive root makes them importable.

variable "image_repository" {
  type = string
}

variable "image_tag" {
  type = string
}

variable "tool_id" {
  type = string
}

# Absolute or repo-relative path to the source zip produced by
# `python3 utils/powerlifting-app/lambda/fission-deploy.py`
# (terraform/fission-build/<tool_id>.zip). The zip already contains:
#   main.py, tool_id.txt, build.sh, <tool_id>/..., <layer modules>, requirements.txt
variable "source_archive" {
  type = string
}

variable "tag_latest" {
  type    = bool
  default = false
}

# python:3.13-slim matches the python-env runtime's interpreter (3.13) so the
# wheels we pip-install here are ABI-compatible with the runtime that actually
# executes the code. The image is only a CARRIER for the deploy archive fs —
# the fission python-env runtime image stays as the Function podspec image.
source "docker" "pl_fn" {
  image    = "public.ecr.aws/docker/library/python:3.13-slim"
  commit   = true
  platform = "linux/amd64"
  changes = [
    "ENV PATH=/usr/local/bin:/usr/bin:/bin",
    "ENV PYTHONDONTWRITEBYTECODE=1",
    "ENV PYTHONUNBUFFERED=1"
  ]
}

build {
  name    = "pl-fn"
  sources = ["source.docker.pl_fn"]

  provisioner "shell" {
    inline = [
      "apt-get update -qq && apt-get install -y -qq unzip ca-certificates >/dev/null 2>&1",
      "rm -rf /var/lib/apt/lists/*",
      "mkdir -p /userfunc/deployarchive"
    ]
  }

  # Upload the pre-built source zip into the build container.
  provisioner "file" {
    source      = var.source_archive
    destination = "/tmp/src.zip"
  }

  # Unzip the archive into /userfunc/deployarchive so the layout exactly
  # matches what fission_entry.py and the fission newdeploy runtime expect,
  # then pip-install the tool's requirements INTO that directory so every dep
  # (boto3, scipy, numpy, pandas, ...) lands at the archive root and is
  # importable by the runtime (sys.path includes /userfunc and the deploy dir).
  provisioner "shell" {
    inline = [
      "cd /userfunc/deployarchive",
      "unzip -q -o /tmp/src.zip",
      # requirements.txt is at the archive root after unzip
      "if [ -f requirements.txt ]; then pip install --no-cache-dir --target=/userfunc/deployarchive -r requirements.txt; fi",
      "rm -f /tmp/src.zip",
      # Sanity: prove the entry + tool + deps are present
      "test -f /userfunc/deployarchive/main.py",
      "test -f /userfunc/deployarchive/tool_id.txt",
      "test -d /userfunc/deployarchive/${var.tool_id}",
      "echo '${var.tool_id}' > /userfunc/deployarchive/tool_id.txt",
      "find /userfunc/deployarchive -maxdepth 1 -name '*.py' | head"
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
