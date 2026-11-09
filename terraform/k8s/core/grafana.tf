resource "kubernetes_config_map_v1" "grafana_datasources" {
  metadata {
    name      = "grafana-datasources"
    namespace = kubernetes_namespace_v1.monitoring.metadata[0].name
  }

  data = {
    "datasources.yaml" = <<-EOT
apiVersion: 1

deleteDatasources:
  - name: Prometheus
    orgId: 1
  - name: Loki
    orgId: 1

datasources:
  - name: Prometheus
    uid: prometheus
    type: prometheus
    access: proxy
    url: http://prometheus.${kubernetes_namespace_v1.monitoring.metadata[0].name}.svc.cluster.local:9090
    isDefault: true
    editable: true
    jsonData:
      timeInterval: 15s
  - name: Loki
    uid: loki
    type: loki
    access: proxy
    url: http://loki.${kubernetes_namespace_v1.monitoring.metadata[0].name}.svc.cluster.local:3100
    editable: true
    jsonData:
      maxLines: 1000
    EOT
  }
}

resource "kubernetes_config_map_v1" "grafana_dashboards" {
  metadata {
    name      = "grafana-dashboards"
    namespace = kubernetes_namespace_v1.monitoring.metadata[0].name
  }

  data = {
    "container-logs.json" = <<-EOT
{
  "annotations": {"list": []},
  "editable": true,
  "title": "Container Logs",
  "uid": "container-logs",
  "schemaVersion": 39,
  "tags": ["loki", "kubernetes"],
  "time": {"from": "now-1h", "to": "now"},
  "panels": [
    {
      "datasource": {"type": "loki", "uid": "loki"},
      "fieldConfig": {"defaults": {}, "overrides": []},
      "gridPos": {"h": 24, "w": 24, "x": 0, "y": 0},
      "id": 1,
      "options": {
        "showLabels": true,
        "showTime": true,
        "sortOrder": "Descending",
        "wrapLogMessage": true,
        "prettifyLogMessage": false,
        "enableLogDetails": true,
        "dedupStrategy": "none"
      },
      "targets": [
        {
          "datasource": {"type": "loki", "uid": "loki"},
          "expr": "{namespace=~\"$namespace\", pod=~\"$pod\", container=~\"$container\"}",
          "queryType": "range",
          "refId": "A"
        }
      ],
      "title": "Logs",
      "type": "logs"
    }
  ],
  "templating": {
    "list": [
      {
        "name": "namespace",
        "type": "query",
        "datasource": {"type": "loki", "uid": "loki"},
        "query": "label_values(namespace)",
        "refresh": 1,
        "includeAll": true,
        "multi": true
      },
      {
        "name": "pod",
        "type": "query",
        "datasource": {"type": "loki", "uid": "loki"},
        "query": "label_values(pod)",
        "refresh": 1,
        "includeAll": true,
        "multi": true
      },
      {
        "name": "container",
        "type": "query",
        "datasource": {"type": "loki", "uid": "loki"},
        "query": "label_values(container)",
        "refresh": 1,
        "includeAll": true,
        "multi": true
      }
    ]
  }
}
    EOT

    "dashboards.yaml" = <<-EOT
apiVersion: 1
providers:
  - name: default
    orgId: 1
    folder: Kubernetes
    type: file
    disableDeletion: false
    updateIntervalSeconds: 60
    allowUiUpdates: false
    options:
      path: /etc/grafana/provisioning/dashboards
    EOT

    "node-exporter-full.json"     = file("${path.module}/dashboards/node-exporter-full.json")
    "kube-state-metrics.json"     = file("${path.module}/dashboards/kube-state-metrics.json")
    "kubernetes-pod-metrics.json" = file("${path.module}/dashboards/kubernetes-pod-metrics.json")
    "ai-calls.json"               = file("${path.module}/dashboards/ai-calls.json")
  }
}

resource "kubernetes_persistent_volume_claim_v1" "grafana_data" {
  metadata {
    name      = "grafana-data"
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
        storage = "${var.grafana_storage_gb}Gi"
      }
    }
  }
}

resource "kubernetes_deployment_v1" "grafana" {
  metadata {
    name      = "grafana"
    namespace = kubernetes_namespace_v1.monitoring.metadata[0].name
    labels    = { app = "grafana" }
  }

  spec {
    replicas = 1
    selector { match_labels = { app = "grafana" } }

    template {
      metadata {
        labels = { app = "grafana" }
        annotations = {
          "grafana-datasources-hash" = sha256(kubernetes_config_map_v1.grafana_datasources.data["datasources.yaml"])
          "grafana-dashboards-hash"  = sha256(jsonencode(kubernetes_config_map_v1.grafana_dashboards.data))
        }
      }

      spec {
        security_context {
          fs_group = 472
        }

        volume {
          name = "datasources"
          config_map {
            name = kubernetes_config_map_v1.grafana_datasources.metadata[0].name
          }
        }

        volume {
          name = "dashboards"
          config_map {
            name = kubernetes_config_map_v1.grafana_dashboards.metadata[0].name
          }
        }

        volume {
          name = "data"
          persistent_volume_claim {
            claim_name = kubernetes_persistent_volume_claim_v1.grafana_data.metadata[0].name
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
            value = "http://localhost:3000/"
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
            name       = "dashboards"
            mount_path = "/etc/grafana/provisioning/dashboards"
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

resource "kubernetes_service_v1" "grafana" {
  metadata {
    name      = "grafana"
    namespace = kubernetes_namespace_v1.monitoring.metadata[0].name
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
