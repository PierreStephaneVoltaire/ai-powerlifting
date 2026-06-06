resource "kubernetes_namespace" "monitoring" {
  metadata {
    name = "monitoring"
    labels = {
      app        = "observability"
      managed-by = "terraform"
    }
  }
}

resource "kubernetes_config_map" "loki_config" {
  metadata {
    name      = "loki-config"
    namespace = kubernetes_namespace.monitoring.metadata[0].name
  }

  data = {
    "loki.yaml" = <<-EOT
auth_enabled: false

server:
  http_listen_port: 3100
  log_level: warn

common:
  path_prefix: /loki
  storage:
    filesystem:
      chunks_directory: /loki/chunks
      rules_directory: /loki/rules
  replication_factor: 1
  ring:
    kvstore:
      store: inmemory

schema_config:
  configs:
    - from: "2024-01-01"
      store: tsdb
      object_store: filesystem
      schema: v13
      index:
        prefix: index_
        period: 24h

limits_config:
  retention_period: ${var.log_retention_days * 24}h
  max_query_length: 721h
  ingestion_rate_mb: 10
  ingestion_burst_size_mb: 20

compactor:
  working_directory: /loki/compactor
  compaction_interval: 10m
  retention_enabled: true
  retention_delete_delay: 2h
  retention_delete_worker_count: 150
  delete_request_store: filesystem
    EOT
  }
}

resource "kubernetes_persistent_volume_claim" "loki_data" {
  metadata {
    name      = "loki-data"
    namespace = kubernetes_namespace.monitoring.metadata[0].name
    annotations = {
      "volume.kubernetes.io/selected-node" = var.node_name
    }
  }

  spec {
    access_modes       = ["ReadWriteOnce"]
    storage_class_name = var.storage_class

    resources {
      requests = {
        storage = "${var.loki_storage_gb}Gi"
      }
    }
  }
}

resource "kubernetes_deployment" "loki" {
  metadata {
    name      = "loki"
    namespace = kubernetes_namespace.monitoring.metadata[0].name
    labels    = { app = "loki" }
  }

  spec {
    replicas = 1
    selector { match_labels = { app = "loki" } }

    template {
      metadata {
        labels = { app = "loki" }
      }

      spec {
        security_context {
          fs_group = 10001
        }

        volume {
          name = "config"
          config_map {
            name = kubernetes_config_map.loki_config.metadata[0].name
          }
        }

        volume {
          name = "data"
          persistent_volume_claim {
            claim_name = kubernetes_persistent_volume_claim.loki_data.metadata[0].name
          }
        }

        container {
          name  = "loki"
          image = "grafana/loki:3.0.0"
          args  = ["-config.file=/etc/loki/loki.yaml"]

          port {
            container_port = 3100
            name           = "http"
          }

          volume_mount {
            name       = "config"
            mount_path = "/etc/loki"
            read_only  = true
          }

          volume_mount {
            name       = "data"
            mount_path = "/loki"
          }

          resources {
            limits = {
              memory = "512Mi"
              cpu    = "500m"
            }
            requests = {
              memory = "256Mi"
              cpu    = "100m"
            }
          }

          readiness_probe {
            http_get {
              path = "/ready"
              port = 3100
            }
            initial_delay_seconds = 15
            period_seconds        = 10
          }

          liveness_probe {
            http_get {
              path = "/ready"
              port = 3100
            }
            initial_delay_seconds = 30
            period_seconds        = 10
          }
        }
      }
    }
  }
}

resource "kubernetes_service" "loki" {
  metadata {
    name      = "loki"
    namespace = kubernetes_namespace.monitoring.metadata[0].name
  }

  spec {
    selector = { app = "loki" }
    port {
      name        = "http"
      port        = 3100
      target_port = 3100
    }
    type = "ClusterIP"
  }
}

resource "kubernetes_service_account" "promtail" {
  metadata {
    name      = "promtail"
    namespace = kubernetes_namespace.monitoring.metadata[0].name
  }
}

resource "kubernetes_cluster_role" "promtail" {
  metadata {
    name = "promtail"
  }

  rule {
    api_groups = [""]
    resources  = ["nodes", "nodes/proxy", "services", "endpoints", "pods"]
    verbs      = ["get", "watch", "list"]
  }
}

resource "kubernetes_cluster_role_binding" "promtail" {
  metadata {
    name = "promtail"
  }

  subject {
    kind      = "ServiceAccount"
    name      = kubernetes_service_account.promtail.metadata[0].name
    namespace = kubernetes_namespace.monitoring.metadata[0].name
  }

  role_ref {
    kind      = "ClusterRole"
    name      = kubernetes_cluster_role.promtail.metadata[0].name
    api_group = "rbac.authorization.k8s.io"
  }
}

resource "kubernetes_config_map" "promtail_config" {
  metadata {
    name      = "promtail-config"
    namespace = kubernetes_namespace.monitoring.metadata[0].name
  }

  data = {
    "promtail.yaml" = <<-EOT
server:
  http_listen_port: 9080
  grpc_listen_port: 0

positions:
  filename: /run/promtail/positions.yaml

clients:
  - url: http://loki.${kubernetes_namespace.monitoring.metadata[0].name}.svc.cluster.local:3100/loki/api/v1/push

scrape_configs:
  - job_name: kubernetes-pods
    kubernetes_sd_configs:
      - role: pod
    pipeline_stages:
      - cri: {}
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_phase]
        regex: 'Succeeded|Failed'
        action: drop
      - source_labels: [__meta_kubernetes_namespace]
        target_label: namespace
      - source_labels: [__meta_kubernetes_pod_name]
        target_label: pod
      - source_labels: [__meta_kubernetes_pod_container_name]
        target_label: container
      - source_labels: [__meta_kubernetes_pod_label_app]
        target_label: app
      - replacement: /var/log/pods/*$1/*.log
        separator: /
        source_labels:
          - __meta_kubernetes_pod_uid
          - __meta_kubernetes_pod_container_name
        target_label: __path__
    EOT
  }
}

resource "kubernetes_daemon_set_v1" "promtail" {
  metadata {
    name      = "promtail"
    namespace = kubernetes_namespace.monitoring.metadata[0].name
    labels    = { app = "promtail" }
  }

  spec {
    selector { match_labels = { app = "promtail" } }

    template {
      metadata {
        labels = { app = "promtail" }
      }

      spec {
        service_account_name = kubernetes_service_account.promtail.metadata[0].name

        toleration {
          effect   = "NoSchedule"
          operator = "Exists"
        }

        volume {
          name = "config"
          config_map {
            name = kubernetes_config_map.promtail_config.metadata[0].name
          }
        }

        volume {
          name = "run"
          host_path {
            path = "/run/promtail"
          }
        }

        volume {
          name = "pods"
          host_path {
            path = "/var/log/pods"
          }
        }

        volume {
          name = "containers"
          host_path {
            path = "/var/log/containers"
          }
        }

        container {
          name  = "promtail"
          image = "grafana/promtail:3.0.0"
          args  = ["-config.file=/etc/promtail/promtail.yaml"]

          security_context {
            run_as_user  = 0
            run_as_group = 0
          }

          port {
            container_port = 9080
            name           = "http"
          }

          volume_mount {
            name       = "config"
            mount_path = "/etc/promtail"
            read_only  = true
          }

          volume_mount {
            name       = "run"
            mount_path = "/run/promtail"
          }

          volume_mount {
            name       = "pods"
            mount_path = "/var/log/pods"
            read_only  = true
          }

          volume_mount {
            name       = "containers"
            mount_path = "/var/log/containers"
            read_only  = true
          }

          resources {
            limits = {
              memory = "128Mi"
              cpu    = "200m"
            }
            requests = {
              memory = "64Mi"
              cpu    = "50m"
            }
          }

          readiness_probe {
            http_get {
              path = "/ready"
              port = 9080
            }
            initial_delay_seconds = 10
            period_seconds        = 10
          }
        }
      }
    }
  }
}

resource "kubernetes_service_account" "prometheus" {
  metadata {
    name      = "prometheus"
    namespace = kubernetes_namespace.monitoring.metadata[0].name
  }
}

resource "kubernetes_cluster_role" "prometheus" {
  metadata {
    name = "prometheus"
  }

  rule {
    api_groups = [""]
    resources  = ["nodes", "nodes/proxy", "nodes/metrics", "services", "endpoints", "pods"]
    verbs      = ["get", "list", "watch"]
  }

  rule {
    api_groups = ["extensions", "networking.k8s.io"]
    resources  = ["ingresses"]
    verbs      = ["get", "list", "watch"]
  }

  rule {
    non_resource_urls = ["/metrics"]
    verbs             = ["get"]
  }
}

resource "kubernetes_cluster_role_binding" "prometheus" {
  metadata {
    name = "prometheus"
  }

  subject {
    kind      = "ServiceAccount"
    name      = kubernetes_service_account.prometheus.metadata[0].name
    namespace = kubernetes_namespace.monitoring.metadata[0].name
  }

  role_ref {
    kind      = "ClusterRole"
    name      = kubernetes_cluster_role.prometheus.metadata[0].name
    api_group = "rbac.authorization.k8s.io"
  }
}

resource "kubernetes_config_map" "prometheus_config" {
  metadata {
    name      = "prometheus-config"
    namespace = kubernetes_namespace.monitoring.metadata[0].name
  }

  data = {
    "prometheus.yml" = <<-EOT
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  - job_name: 'nginx-gateway'
    kubernetes_sd_configs:
      - role: pod
        namespaces:
          names:
            - ${kubernetes_namespace.nginx_gateway.metadata[0].name}
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_label_app_kubernetes_io_name]
        regex: nginx-gateway-fabric
        action: keep
      - source_labels: [__meta_kubernetes_pod_container_port_number]
        regex: '9113'
        action: keep
      - source_labels: [__meta_kubernetes_namespace]
        target_label: namespace
      - source_labels: [__meta_kubernetes_pod_name]
        target_label: pod

  - job_name: 'tinyauth'
    static_configs:
      - targets: ['tinyauth.${kubernetes_namespace.if_portals.metadata[0].name}.svc.cluster.local:3000']
    metrics_path: /metrics

  - job_name: 'portal-backends'
    kubernetes_sd_configs:
      - role: pod
        namespaces:
          names:
            - ${kubernetes_namespace.if_portals.metadata[0].name}
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_scrape]
        action: keep
        regex: "true"
      - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_path]
        action: replace
        target_label: __metrics_path__
        regex: (.+)
      - source_labels: [__address__, __meta_kubernetes_pod_annotation_prometheus_io_port]
        action: replace
        regex: (.+?)(?::\d+)?;(\d+)
        replacement: $1:$2
        target_label: __address__
      - source_labels: [__meta_kubernetes_namespace]
        target_label: namespace
      - source_labels: [__meta_kubernetes_pod_name]
        target_label: pod
      - source_labels: [__meta_kubernetes_pod_label_app]
        target_label: app
    EOT
  }
}

resource "kubernetes_persistent_volume_claim" "prometheus_data" {
  metadata {
    name      = "prometheus-data"
    namespace = kubernetes_namespace.monitoring.metadata[0].name
    annotations = {
      "volume.kubernetes.io/selected-node" = var.node_name
    }
  }

  spec {
    access_modes       = ["ReadWriteOnce"]
    storage_class_name = var.storage_class

    resources {
      requests = {
        storage = "${var.prometheus_storage_gb}Gi"
      }
    }
  }
}

resource "kubernetes_deployment" "prometheus" {
  metadata {
    name      = "prometheus"
    namespace = kubernetes_namespace.monitoring.metadata[0].name
    labels    = { app = "prometheus" }
  }

  spec {
    replicas = 1
    selector { match_labels = { app = "prometheus" } }

    template {
      metadata {
        labels = { app = "prometheus" }
      }

      spec {
        service_account_name = kubernetes_service_account.prometheus.metadata[0].name

        security_context {
          fs_group     = 65534
          run_as_user  = 65534
          run_as_group = 65534
        }

        volume {
          name = "config"
          config_map {
            name = kubernetes_config_map.prometheus_config.metadata[0].name
          }
        }

        volume {
          name = "data"
          persistent_volume_claim {
            claim_name = kubernetes_persistent_volume_claim.prometheus_data.metadata[0].name
          }
        }

        container {
          name  = "prometheus"
          image = "prom/prometheus:v2.53.0"
          args = [
            "--config.file=/etc/prometheus/prometheus.yml",
            "--storage.tsdb.path=/prometheus",
            "--storage.tsdb.retention.time=${var.metrics_retention_days}d",
            "--web.console.libraries=/etc/prometheus/console_libraries",
            "--web.console.templates=/etc/prometheus/consoles",
            "--web.enable-lifecycle",
          ]

          port {
            container_port = 9090
            name           = "http"
          }

          volume_mount {
            name       = "config"
            mount_path = "/etc/prometheus"
            read_only  = true
          }

          volume_mount {
            name       = "data"
            mount_path = "/prometheus"
          }

          resources {
            limits = {
              memory = "512Mi"
              cpu    = "500m"
            }
            requests = {
              memory = "256Mi"
              cpu    = "100m"
            }
          }

          readiness_probe {
            http_get {
              path = "/-/ready"
              port = 9090
            }
            initial_delay_seconds = 10
            period_seconds        = 5
          }

          liveness_probe {
            http_get {
              path = "/-/healthy"
              port = 9090
            }
            initial_delay_seconds = 30
            period_seconds        = 15
          }
        }
      }
    }
  }
}

resource "kubernetes_service" "prometheus" {
  metadata {
    name      = "prometheus"
    namespace = kubernetes_namespace.monitoring.metadata[0].name
  }

  spec {
    selector = { app = "prometheus" }
    port {
      name        = "http"
      port        = 9090
      target_port = 9090
    }
    type = "ClusterIP"
  }
}

resource "kubernetes_config_map" "grafana_datasources" {
  metadata {
    name      = "grafana-datasources"
    namespace = kubernetes_namespace.monitoring.metadata[0].name
  }

  data = {
    "datasources.yaml" = <<-EOT
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus.${kubernetes_namespace.monitoring.metadata[0].name}.svc.cluster.local:9090
    isDefault: true
    editable: true
  - name: Loki
    type: loki
    access: proxy
    url: http://loki.${kubernetes_namespace.monitoring.metadata[0].name}.svc.cluster.local:3100
    editable: true
    EOT
  }
}

resource "kubernetes_persistent_volume_claim" "grafana_data" {
  metadata {
    name      = "grafana-data"
    namespace = kubernetes_namespace.monitoring.metadata[0].name
    annotations = {
      "volume.kubernetes.io/selected-node" = var.node_name
    }
  }

  spec {
    access_modes       = ["ReadWriteOnce"]
    storage_class_name = var.storage_class

    resources {
      requests = {
        storage = "${var.grafana_storage_gb}Gi"
      }
    }
  }
}

resource "kubernetes_deployment" "grafana" {
  metadata {
    name      = "grafana"
    namespace = kubernetes_namespace.monitoring.metadata[0].name
    labels    = { app = "grafana" }
  }

  spec {
    replicas = 1
    selector { match_labels = { app = "grafana" } }

    template {
      metadata {
        labels = { app = "grafana" }
      }

      spec {
        security_context {
          fs_group = 472
        }

        volume {
          name = "datasources"
          config_map {
            name = kubernetes_config_map.grafana_datasources.metadata[0].name
          }
        }

        volume {
          name = "data"
          persistent_volume_claim {
            claim_name = kubernetes_persistent_volume_claim.grafana_data.metadata[0].name
          }
        }

        container {
          name  = "grafana"
          image = "grafana/grafana:11.0.0"

          port {
            container_port = 3000
            name           = "http"
          }

          env {
            name  = "GF_SECURITY_ADMIN_PASSWORD"
            value = var.grafana_admin_password
          }

          env {
            name  = "GF_SERVER_ROOT_URL"
            value = "https://${local.logs_domain}/"
          }

          env {
            name  = "GF_SERVER_SERVE_FROM_SUB_PATH"
            value = "false"
          }

          volume_mount {
            name       = "datasources"
            mount_path = "/etc/grafana/provisioning/datasources"
            read_only  = true
          }

          volume_mount {
            name       = "data"
            mount_path = "/var/lib/grafana"
          }

          resources {
            limits = {
              memory = "256Mi"
              cpu    = "250m"
            }
            requests = {
              memory = "128Mi"
              cpu    = "50m"
            }
          }

          readiness_probe {
            http_get {
              path = "/api/health"
              port = 3000
            }
            initial_delay_seconds = 10
            period_seconds        = 10
          }

          liveness_probe {
            http_get {
              path = "/api/health"
              port = 3000
            }
            initial_delay_seconds = 30
            period_seconds        = 10
          }
        }
      }
    }
  }
}

resource "kubernetes_service" "grafana" {
  metadata {
    name      = "grafana"
    namespace = kubernetes_namespace.monitoring.metadata[0].name
  }

  spec {
    selector = { app = "grafana" }
    port {
      name        = "http"
      port        = 3000
      target_port = 3000
    }
    type = "ClusterIP"
  }
}

resource "kubectl_manifest" "monitoring_reference_grant" {
  yaml_body = <<-YAML
apiVersion: gateway.networking.k8s.io/v1beta1
kind: ReferenceGrant
metadata:
  name: allow-if-portals-routes
  namespace: ${kubernetes_namespace.monitoring.metadata[0].name}
spec:
  from:
    - group: gateway.networking.k8s.io
      kind: HTTPRoute
      namespace: ${kubernetes_namespace.if_portals.metadata[0].name}
  to:
    - group: ""
      kind: Service
  YAML
}

# ─── Kubernetes Event Exporter ────────────────────────────────────────────────
# Watches Kubernetes events and forwards them to Loki so they appear in Grafana
# alongside pod logs. Uses resmoio/kubernetes-event-exporter (v1.7).

resource "kubernetes_service_account" "event_exporter" {
  metadata {
    name      = "event-exporter"
    namespace = kubernetes_namespace.monitoring.metadata[0].name
  }
}

resource "kubernetes_cluster_role" "event_exporter" {
  metadata {
    name = "event-exporter"
  }

  rule {
    api_groups = [""]
    resources  = ["events"]
    verbs      = ["get", "watch", "list"]
  }

  rule {
    api_groups = ["coordination.k8s.io"]
    resources  = ["leases"]
    verbs      = ["get", "create", "update", "patch", "delete"]
  }
}

resource "kubernetes_cluster_role_binding" "event_exporter" {
  metadata {
    name = "event-exporter"
  }

  subject {
    kind      = "ServiceAccount"
    name      = kubernetes_service_account.event_exporter.metadata[0].name
    namespace = kubernetes_namespace.monitoring.metadata[0].name
  }

  role_ref {
    kind      = "ClusterRole"
    name      = kubernetes_cluster_role.event_exporter.metadata[0].name
    api_group = "rbac.authorization.k8s.io"
  }
}

resource "kubernetes_config_map" "event_exporter_config" {
  metadata {
    name      = "event-exporter-cfg"
    namespace = kubernetes_namespace.monitoring.metadata[0].name
  }

  data = {
    "config.yaml" = <<-EOT
logLevel: info
logFormat: json
maxEventAgeSeconds: 5
route:
  routes:
    - match:
        - receiver: "loki"
receivers:
  - name: "loki"
    loki:
      url: http://loki.${kubernetes_namespace.monitoring.metadata[0].name}.svc.cluster.local:3100/loki/api/v1/push
      streamLabels:
        job: kubernetes-events
        namespace: '{{ .Namespace }}'
        type: '{{ .Type }}'
        reason: '{{ .Reason }}'
    EOT
  }
}

resource "kubernetes_deployment" "event_exporter" {
  metadata {
    name      = "event-exporter"
    namespace = kubernetes_namespace.monitoring.metadata[0].name
    labels    = { app = "event-exporter" }
  }

  spec {
    replicas = 1
    selector { match_labels = { app = "event-exporter" } }

    template {
      metadata {
        labels = { app = "event-exporter" }
        annotations = {
          "prometheus.io/scrape" = "true"
          "prometheus.io/port"   = "2112"
          "prometheus.io/path"   = "/metrics"
        }
      }

      spec {
        service_account_name = kubernetes_service_account.event_exporter.metadata[0].name

        security_context {
          run_as_non_root = true
          seccomp_profile {
            type = "RuntimeDefault"
          }
        }

        volume {
          name = "cfg"
          config_map {
            name = kubernetes_config_map.event_exporter_config.metadata[0].name
          }
        }

        container {
          name  = "event-exporter"
          image = "ghcr.io/resmoio/kubernetes-event-exporter:v1.7"
          args  = ["-conf=/data/config.yaml"]

          security_context {
            allow_privilege_escalation = false
            capabilities {
              drop = ["ALL"]
            }
          }

          volume_mount {
            name       = "cfg"
            mount_path = "/data"
            read_only  = true
          }

          resources {
            limits = {
              memory = "128Mi"
              cpu    = "200m"
            }
            requests = {
              memory = "64Mi"
              cpu    = "50m"
            }
          }

          readiness_probe {
            http_get {
              path = "/metrics"
              port = 2112
            }
            initial_delay_seconds = 5
            period_seconds        = 10
          }

          liveness_probe {
            http_get {
              path = "/metrics"
              port = 2112
            }
            initial_delay_seconds = 15
            period_seconds        = 10
          }
        }
      }
    }
  }
}
