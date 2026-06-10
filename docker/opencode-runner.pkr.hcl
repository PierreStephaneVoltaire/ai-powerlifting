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

variable "gh_version" {
  type    = string
  default = "2.67.0"
}

variable "kubectl_version" {
  type    = string
  default = "1.31.4"
}

variable "rust_toolchain" {
  type    = string
  default = "stable"
}

# node:20-bookworm-slim is the runtime base. We still need Node because
# opencode-ai is a Node.js package; the opencode-runner HTTP wrapper
# itself is a Rust binary that we build and copy in below.
source "docker" "opencode_runner" {
  image    = "public.ecr.aws/docker/library/node:20-bookworm-slim"
  commit   = true
  platform = "linux/amd64"
  changes = [
    "WORKDIR /app",
    "ENV PATH=/usr/local/bin:$PATH",
    "EXPOSE 8000",
    "CMD [\"/app/opencode-runner\"]"
  ]
}

build {
  name    = "if-opencode-runner"
  sources = ["source.docker.opencode_runner"]

  # Runtime system packages: what the Fission-spawned OpenCode job needs
  # to run opencode, talk to AWS, do git operations, and read PVCs.
  # Deliberately omits terraform, jre, golang, nmap, tcpdump, traceroute,
  # and other tools the api-agent image carries for specialist workflows.
  provisioner "shell" {
    inline = [
      "export DEBIAN_FRONTEND=noninteractive && apt-get update && apt-get install -y curl unzip ca-certificates git jq wget",
      "rm -rf /var/lib/apt/lists/*",
      "mkdir -p /app"
    ]
  }

  # GitHub CLI for repo operations during specialist runs.
  provisioner "shell" {
    inline = [
      "curl -fsSL https://github.com/cli/cli/releases/download/v${var.gh_version}/gh_${var.gh_version}_linux_amd64.tar.gz -o /tmp/gh.tar.gz",
      "tar -xzf /tmp/gh.tar.gz -C /tmp",
      "cp /tmp/gh_${var.gh_version}_linux_amd64/bin/gh /usr/local/bin/gh",
      "gh --version",
      "rm -rf /tmp/gh*"
    ]
  }

  # kubectl for diagnostics — the runner does not manage the cluster, but
  # it is useful to inspect Fission/executor state from inside a job pod
  # when debugging.
  provisioner "shell" {
    inline = [
      "curl -fsSL https://dl.k8s.io/release/v${var.kubectl_version}/bin/linux/amd64/kubectl -o /usr/local/bin/kubectl",
      "chmod +x /usr/local/bin/kubectl",
      "kubectl version --client"
    ]
  }

  # OpenCode runtime. Same version the api-agent image uses so the two
  # stay in lockstep; bump both in lockstep when upgrading.
  provisioner "shell" {
    inline = [
      "npm install -g opencode-ai@${var.opencode_version}",
      "opencode --version"
    ]
  }

  # ---- Build the opencode-runner Rust binary ----
  # The build runs inside the Packer build container. The resulting
  # binary is the only artifact we keep; everything else (cargo
  # registry, target/, rustup, build-essentials) is purged at the end
  # of this block so the final image stays slim.

  # C toolchain for the final link step. tiny_http + serde are pure
  # Rust, but the linker still needs cc.
  provisioner "shell" {
    inline = [
      "export DEBIAN_FRONTEND=noninteractive && apt-get update && apt-get install -y build-essential pkg-config",
      "rm -rf /var/lib/apt/lists/*"
    ]
  }

  # Rust toolchain. Pinned via var.rust_toolchain (default: stable).
  provisioner "shell" {
    inline = [
      "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain ${var.rust_toolchain} --profile minimal --no-modify-path",
      "export PATH=\"/root/.cargo/bin:$PATH\"",
      "rustc --version",
      "cargo --version"
    ]
  }

  # Copy the Rust source tree into the build container.
  provisioner "file" {
    source      = "../utils/opencode-runner"
    destination = "/build/opencode-runner"
  }

  # Compile the release binary. ~5 MB stripped static binary; no
  # runtime deps needed.
  provisioner "shell" {
    inline = [
      "export PATH=\"/root/.cargo/bin:$PATH\"",
      "export CARGO_HOME=/root/.cargo",
      "cd /build/opencode-runner",
      "cargo build --release --locked",
      "ls -la target/release/opencode-runner",
      "strip target/release/opencode-runner",
      "cp target/release/opencode-runner /app/opencode-runner",
      "chmod +x /app/opencode-runner",
      "ls -la /app/opencode-runner"
    ]
  }

  # Drop the build toolchain so the final image only contains the
  # binary. Keeps the image lean and reduces attack surface.
  provisioner "shell" {
    inline = [
      "export DEBIAN_FRONTEND=noninteractive",
      "rm -rf /build",
      "rm -rf /root/.cargo /root/.rustup",
      "apt-get purge -y build-essential pkg-config",
      "apt-get autoremove -y",
      "rm -rf /var/lib/apt/lists/* /root/.cache"
    ]
  }

  # Same read-only data the api-agent mounts, so Fission-spawned job pods
  # resolve the same specialists / models / skills / scripts / tools the
  # IF agent uses. Packer bakes them into the image; the Fission function
  # pod additionally bind-mounts the live workspace PVCs.
  provisioner "file" {
    source      = "../specialists"
    destination = "/app/specialists"
  }
  provisioner "file" {
    source      = "../tools"
    destination = "/app/tools"
  }
  provisioner "file" {
    source      = "../models"
    destination = "/app/models"
  }
  provisioner "file" {
    source      = "../skills"
    destination = "/app/skills"
  }
  provisioner "file" {
    source      = "../scripts"
    destination = "/app/scripts"
  }

  # Pre-create the workspace directories so the Fission function can
  # write to them immediately, regardless of which PVC bind-mount the
  # executor attaches.
  provisioner "shell" {
    inline = [
      "mkdir -p /app/src/data/conversations",
      "mkdir -p /app/src/data",
      "mkdir -p /app/src/sandbox"
    ]
  }

  # Drop a marker so the Fission health probe and humans can tell that
  # the pod is the runner image and not the api-agent.
  provisioner "shell" {
    inline = [
      "echo 'if-opencode-runner' > /app/IMAGE_KIND"
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
