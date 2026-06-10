

resource "kubernetes_namespace" "fission" {
  count = var.fission_enabled ? 1 : 0

  metadata {
    name = var.fission_namespace
    labels = {
      app        = "fission"
      managed-by = "terraform"
    }
  }
}


resource "null_resource" "fission_crds" {
  count = var.fission_enabled ? 1 : 0

  triggers = {
    fission_version = var.fission_version
  }

  provisioner "local-exec" {
    command = <<-EOT
      kubectl create -k "github.com/fission/fission/crds/v1?ref=v${var.fission_version}" --validate=false || true
    EOT
  }

  depends_on = [kubernetes_namespace.fission]
}

resource "helm_release" "fission" {
  count = var.fission_enabled ? 1 : 0

  name       = "fission"
  namespace  = kubernetes_namespace.fission[0].metadata[0].name
  repository = "https://fission.github.io/fission-charts"
  chart      = "fission-all"
  version    = var.fission_version


  set {
    name  = "serviceType"
    value = "ClusterIP"
  }
  set {
    name  = "routerServiceType"
    value = "ClusterIP"
  }


  set {
    name  = "defaultNamespace"
    value = var.fission_function_namespace
  }


  set {
    name  = "router.roundTrip.timeout"
    value = "${var.fission_router_timeout_seconds * 1000}ms"
  }
  set {
    name  = "router.roundTrip.maxRetries"
    value = "0"
  }


  set {
    name  = "persistence.enabled"
    value = "true"
  }
  set {
    name  = "persistence.storageClassName"
    value = var.storage_class
  }
  set {
    name  = "persistence.size"
    value = "5Gi"
  }


  set {
    name  = "executor.resources.requests.memory"
    value = "256Mi"
  }
  set {
    name  = "executor.resources.limits.memory"
    value = "512Mi"
  }
  set {
    name  = "router.resources.requests.memory"
    value = "128Mi"
  }
  set {
    name  = "router.resources.limits.memory"
    value = "512Mi"
  }

  depends_on = [
    null_resource.fission_crds,
  ]
}



resource "kubectl_manifest" "fission_environment_opencode_runner" {
  count = var.fission_enabled ? 1 : 0

  yaml_body = <<-YAML
    apiVersion: fission.io/v1
    kind: Environment
    metadata:
      name: ${var.fission_environment_name}
      namespace: ${var.fission_namespace}
    spec:
      runtime:
        name: newdeploy
      image: ${aws_ecr_repository.if_opencode_runner.repository_url}:latest
      imagePullPolicy: IfNotPresent
      # keeparchive is left at its default (false): the runner is a baked
      # image, not a build-from-source environment.
  YAML

  depends_on = [helm_release.fission]
}


resource "kubectl_manifest" "fission_function_opencode_job" {
  count = var.fission_enabled ? 1 : 0

  yaml_body = <<-YAML
    apiVersion: fission.io/v1
    kind: Function
    metadata:
      name: ${var.fission_function_name}
      namespace: ${var.fission_function_namespace}
    spec:
      environment: ${var.fission_environment_name}
      # The function's podspec is what the newdeploy executor uses to spin
      # up the function Deployment. Mounts mirror the IF agent deployment
      # so the opencode subprocess sees the same workspace and credentials.
      podspec:
        containers:
          - name: opencode-runner
            image: ${aws_ecr_repository.if_opencode_runner.repository_url}:latest
            imagePullPolicy: IfNotPresent
            command: ["node", "/app/server.js"]
            ports:
              - containerPort: 8000
            env:
              - name: PORT
                value: "8000"
              - name: HOST
                value: "0.0.0.0"
              - name: OPENCODE_WORKSPACE_BASE
                value: "/app/src/data/conversations"
            envFrom:
              - secretRef:
                  name: ${kubernetes_secret.if_agent_api_secrets.metadata[0].name}
              - configMapRef:
                  name: ${kubernetes_config_map.if_agent_api_config.metadata[0].name}
              - configMapRef:
                  name: ${kubernetes_config_map.if_agent_api_model_config.metadata[0].name}
            resources:
              limits:
                memory: ${var.opencode_runner_memory_mb}Mi
                cpu: ${var.opencode_runner_cpu_millicores}m
              requests:
                memory: ${var.opencode_runner_memory_request_mb}Mi
                cpu: ${var.opencode_runner_cpu_request_millicores}m
            volumeMounts:
              - name: data-storage
                mountPath: /app/src/data
              - name: sandbox-storage
                mountPath: /app/src/sandbox
              - name: conversations-storage
                mountPath: /app/src/data/conversations
              - name: facts-storage
                mountPath: /app/src/data/facts
              - name: aws-credentials
                mountPath: /root/.aws
                readOnly: true
        imagePullSecrets:
          - name: ${kubernetes_secret.ecr_registry.metadata[0].name}
        # No nodeSelector: this is a single-node k3s cluster so every pod
        # lands on the same node as the IF agent anyway, which means the
        # local-path PVCs and the aws-credentials host path both resolve
        # without explicit scheduling hints.
        volumes:
          - name: data-storage
            persistentVolumeClaim:
              claimName: ${kubernetes_persistent_volume_claim.if_agent_data.metadata[0].name}
          - name: sandbox-storage
            persistentVolumeClaim:
              claimName: ${kubernetes_persistent_volume_claim.if_agent_sandbox.metadata[0].name}
          - name: conversations-storage
            persistentVolumeClaim:
              claimName: ${kubernetes_persistent_volume_claim.if_agent_conversations.metadata[0].name}
          - name: facts-storage
            persistentVolumeClaim:
              claimName: ${kubernetes_persistent_volume_claim.if_agent_facts.metadata[0].name}
          - name: aws-credentials
            hostPath:
              path: ${var.aws_credentials_host_path}
              type: Directory
  YAML

  depends_on = [
    kubectl_manifest.fission_environment_opencode_runner,
    kubernetes_persistent_volume_claim.if_agent_data,
    kubernetes_persistent_volume_claim.if_agent_sandbox,
    kubernetes_persistent_volume_claim.if_agent_conversations,
    kubernetes_persistent_volume_claim.if_agent_facts,
    kubernetes_secret.if_agent_api_secrets,
    kubernetes_config_map.if_agent_api_config,
    kubernetes_config_map.if_agent_api_model_config,
    kubernetes_secret.ecr_registry,
    null_resource.packer_build_opencode_runner,
  ]
}


resource "kubectl_manifest" "fission_http_trigger_opencode_job" {
  count = var.fission_enabled ? 1 : 0

  yaml_body = <<-YAML
    apiVersion: fission.io/v1
    kind: HTTPTrigger
    metadata:
      name: ${var.fission_function_name}
      namespace: ${var.fission_function_namespace}
    spec:
      functionReference:
        functionName: ${var.fission_function_name}
      methods:
        - POST
      url: ${var.fission_http_trigger_url}
  YAML

  depends_on = [kubectl_manifest.fission_function_opencode_job]
}
