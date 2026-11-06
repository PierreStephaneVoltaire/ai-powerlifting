resource "kubernetes_config_map_v1" "loki_config" {
  metadata {
    name      = "loki-config"
    namespace = kubernetes_namespace_v1.monitoring.metadata[0].name
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

resource "kubernetes_persistent_volume_claim_v1" "loki_data" {
  metadata {
    name      = "loki-data"
    namespace = kubernetes_namespace_v1.monitoring.metadata[0].name
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

resource "kubernetes_deployment_v1" "loki" {
  metadata {
    name      = "loki"
    namespace = kubernetes_namespace_v1.monitoring.metadata[0].name
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
            name = kubernetes_config_map_v1.loki_config.metadata[0].name
          }
        }

        volume {
          name = "data"
          persistent_volume_claim {
            claim_name = kubernetes_persistent_volume_claim_v1.loki_data.metadata[0].name
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

resource "kubernetes_service_v1" "loki" {
  metadata {
    name      = "loki"
    namespace = kubernetes_namespace_v1.monitoring.metadata[0].name
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

resource "kubernetes_service_account_v1" "promtail" {
  metadata {
    name      = "promtail"
    namespace = kubernetes_namespace_v1.monitoring.metadata[0].name
  }
}

resource "kubernetes_cluster_role_v1" "promtail" {
  metadata {
    name = "promtail"
  }

  rule {
    api_groups = [""]
    resources  = ["nodes", "nodes/proxy", "services", "endpoints", "pods"]
    verbs      = ["get", "watch", "list"]
  }
}

resource "kubernetes_cluster_role_binding_v1" "promtail" {
  metadata {
    name = "promtail"
  }

  subject {
    kind      = "ServiceAccount"
    name      = kubernetes_service_account_v1.promtail.metadata[0].name
    namespace = kubernetes_namespace_v1.monitoring.metadata[0].name
  }

  role_ref {
    kind      = "ClusterRole"
    name      = kubernetes_cluster_role_v1.promtail.metadata[0].name
    api_group = "rbac.authorization.k8s.io"
  }
}

resource "kubernetes_config_map_v1" "promtail_config" {
  metadata {
    name      = "promtail-config"
    namespace = kubernetes_namespace_v1.monitoring.metadata[0].name
  }

  data = {
    "promtail.yaml" = <<-EOT
server:
  http_listen_port: 9080
  grpc_listen_port: 0
  log_level: info

positions:
  filename: /run/promtail/positions.yaml

clients:
  - url: http://loki.${kubernetes_namespace_v1.monitoring.metadata[0].name}.svc.cluster.local:3100/loki/api/v1/push
    batchwait: 1s
    batchsize: 1048576

scrape_configs:
  - job_name: container-logs
    static_configs:
      - targets:
          - localhost
        labels:
          job: container-logs
          __path__: /var/log/containers/*_${var.namespace}_*.log
      - targets:
          - localhost
        labels:
          job: container-logs
          __path__: /var/log/containers/*_${var.runner_namespace}_*.log
      - targets:
          - localhost
        labels:
          job: container-logs
          __path__: /var/log/containers/*_${var.auth_namespace}_*.log
    pipeline_stages:
      - cri: {}
      - regex:
          source: filename
          expression: '/var/log/containers/(?P<pod>[^_]+)_(?P<namespace>[^_]+)_(?P<container>.+)-[0-9a-f]{64}\.log$'
      - labels:
          pod:
          namespace:
          container:
    relabel_configs:
      - target_label: __address__
        replacement: localhost
    EOT
  }
}

resource "kubernetes_daemon_set_v1" "promtail" {
  metadata {
    name      = "promtail"
    namespace = kubernetes_namespace_v1.monitoring.metadata[0].name
    labels    = { app = "promtail" }
  }

  spec {
    selector { match_labels = { app = "promtail" } }

    template {
      metadata {
        labels = { app = "promtail" }
        annotations = {
          "promtail-config-hash" = sha256(kubernetes_config_map_v1.promtail_config.data["promtail.yaml"])
        }
      }

      spec {
        service_account_name = kubernetes_service_account_v1.promtail.metadata[0].name

        toleration {
          effect   = "NoSchedule"
          operator = "Exists"
        }

        volume {
          name = "config"
          config_map {
            name = kubernetes_config_map_v1.promtail_config.metadata[0].name
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

resource "kubernetes_service_account_v1" "event_exporter" {
  metadata {
    name      = "event-exporter"
    namespace = kubernetes_namespace_v1.monitoring.metadata[0].name
  }
}

resource "kubernetes_cluster_role_v1" "event_exporter" {
  metadata {
    name = "event-exporter"
  }

  rule {
    api_groups = [""]
    resources  = ["events"]
    verbs      = ["get", "watch", "list"]
  }

  rule {
    api_groups = [""]
    resources  = ["pods"]
    verbs      = ["get", "list"]
  }

  rule {
    api_groups = ["apps"]
    resources  = ["deployments", "replicasets", "statefulsets", "daemonsets"]
    verbs      = ["get", "list"]
  }

  rule {
    api_groups = ["coordination.k8s.io"]
    resources  = ["leases"]
    verbs      = ["get", "create", "update", "patch", "delete"]
  }
}

resource "kubernetes_cluster_role_binding_v1" "event_exporter" {
  metadata {
    name = "event-exporter"
  }

  subject {
    kind      = "ServiceAccount"
    name      = kubernetes_service_account_v1.event_exporter.metadata[0].name
    namespace = kubernetes_namespace_v1.monitoring.metadata[0].name
  }

  role_ref {
    kind      = "ClusterRole"
    name      = kubernetes_cluster_role_v1.event_exporter.metadata[0].name
    api_group = "rbac.authorization.k8s.io"
  }
}

resource "kubernetes_config_map_v1" "event_exporter_config" {
  metadata {
    name      = "event-exporter-cfg"
    namespace = kubernetes_namespace_v1.monitoring.metadata[0].name
  }

  data = {
    "config.yaml" = <<-EOT
logLevel: info
logFormat: json
maxEventAgeSeconds: 30
omitLookup: true
route:
  routes:
    - match:
        - receiver: "loki"
receivers:
  - name: "loki"
    loki:
      url: http://loki.${kubernetes_namespace_v1.monitoring.metadata[0].name}.svc.cluster.local:3100/loki/api/v1/push
      streamLabels:
        job: kubernetes-events
    EOT
  }
}

resource "kubernetes_deployment_v1" "event_exporter" {
  metadata {
    name      = "event-exporter"
    namespace = kubernetes_namespace_v1.monitoring.metadata[0].name
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
        service_account_name = kubernetes_service_account_v1.event_exporter.metadata[0].name

        security_context {
          run_as_non_root = true
          seccomp_profile {
            type = "RuntimeDefault"
          }
        }

        volume {
          name = "cfg"
          config_map {
            name = kubernetes_config_map_v1.event_exporter_config.metadata[0].name
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
