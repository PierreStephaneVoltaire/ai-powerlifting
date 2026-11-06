resource "kubernetes_service_account_v1" "prometheus" {
  metadata {
    name      = "prometheus"
    namespace = kubernetes_namespace_v1.monitoring.metadata[0].name
  }
}

resource "kubernetes_cluster_role_v1" "prometheus" {
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

resource "kubernetes_cluster_role_binding_v1" "prometheus" {
  metadata {
    name = "prometheus"
  }

  subject {
    kind      = "ServiceAccount"
    name      = kubernetes_service_account_v1.prometheus.metadata[0].name
    namespace = kubernetes_namespace_v1.monitoring.metadata[0].name
  }

  role_ref {
    kind      = "ClusterRole"
    name      = kubernetes_cluster_role_v1.prometheus.metadata[0].name
    api_group = "rbac.authorization.k8s.io"
  }
}

resource "kubernetes_config_map_v1" "prometheus_config" {
  metadata {
    name      = "prometheus-config"
    namespace = kubernetes_namespace_v1.monitoring.metadata[0].name
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
            - ${var.namespace}
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


  - job_name: 'portal-backends'
    kubernetes_sd_configs:
      - role: pod
        namespaces:
          names:
            - ${var.namespace}
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

  - job_name: 'kube-state-metrics'
    static_configs:
      - targets: ['kube-state-metrics.${kubernetes_namespace_v1.monitoring.metadata[0].name}.svc.cluster.local:8080']
    relabel_configs:
      - target_label: cluster
        replacement: ${var.node_name}

  - job_name: 'node-exporter'
    kubernetes_sd_configs:
      - role: endpoints
        namespaces:
          names:
            - ${kubernetes_namespace_v1.monitoring.metadata[0].name}
    relabel_configs:
      - source_labels: [__meta_kubernetes_service_name]
        action: keep
        regex: node-exporter
      - source_labels: [__meta_kubernetes_endpoint_port_name]
        action: keep
        regex: metrics

  - job_name: 'cadvisor'
    kubernetes_sd_configs:
      - role: endpoints
        namespaces:
          names:
            - ${kubernetes_namespace_v1.monitoring.metadata[0].name}
    relabel_configs:
      - source_labels: [__meta_kubernetes_service_name]
        action: keep
        regex: cadvisor
      - source_labels: [__meta_kubernetes_endpoint_port_name]
        action: keep
        regex: metrics
      - source_labels: [__meta_kubernetes_namespace]
        target_label: namespace
      - source_labels: [__meta_kubernetes_pod_name]
        target_label: pod

    EOT
  }
}

resource "kubernetes_persistent_volume_claim_v1" "prometheus_data" {
  metadata {
    name      = "prometheus-data"
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
        storage = "${var.prometheus_storage_gb}Gi"
      }
    }
  }
}

resource "kubernetes_deployment_v1" "prometheus" {
  metadata {
    name      = "prometheus"
    namespace = kubernetes_namespace_v1.monitoring.metadata[0].name
    labels    = { app = "prometheus" }
  }

  spec {
    replicas = 1
    selector { match_labels = { app = "prometheus" } }
    strategy { type = "Recreate" }

    template {
      metadata {
        labels = { app = "prometheus" }
        annotations = {
          "prometheus-config-hash" = sha256(kubernetes_config_map_v1.prometheus_config.data["prometheus.yml"])
        }
      }

      spec {
        service_account_name = kubernetes_service_account_v1.prometheus.metadata[0].name

        security_context {
          fs_group     = 65534
          run_as_user  = 65534
          run_as_group = 65534
        }

        volume {
          name = "config"
          config_map {
            name = kubernetes_config_map_v1.prometheus_config.metadata[0].name
          }
        }

        volume {
          name = "data"
          persistent_volume_claim {
            claim_name = kubernetes_persistent_volume_claim_v1.prometheus_data.metadata[0].name
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
              memory = "2Gi"
              cpu    = "500m"
            }
            requests = {
              memory = "512Mi"
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

resource "kubernetes_service_v1" "prometheus" {
  metadata {
    name      = "prometheus"
    namespace = kubernetes_namespace_v1.monitoring.metadata[0].name
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

resource "kubernetes_service_account_v1" "kube_state_metrics" {
  metadata {
    name      = "kube-state-metrics"
    namespace = kubernetes_namespace_v1.monitoring.metadata[0].name
  }
}

resource "kubernetes_cluster_role_v1" "kube_state_metrics" {
  metadata {
    name = "kube-state-metrics"
  }

  rule {
    api_groups = ["*"]
    resources  = ["*"]
    verbs      = ["get", "list", "watch"]
  }
}

resource "kubernetes_cluster_role_binding_v1" "kube_state_metrics" {
  metadata {
    name = "kube-state-metrics"
  }

  subject {
    kind      = "ServiceAccount"
    name      = kubernetes_service_account_v1.kube_state_metrics.metadata[0].name
    namespace = kubernetes_namespace_v1.monitoring.metadata[0].name
  }

  role_ref {
    api_group = "rbac.authorization.k8s.io"
    kind      = "ClusterRole"
    name      = kubernetes_cluster_role_v1.kube_state_metrics.metadata[0].name
  }
}

resource "kubernetes_deployment_v1" "kube_state_metrics" {
  metadata {
    name      = "kube-state-metrics"
    namespace = kubernetes_namespace_v1.monitoring.metadata[0].name
    labels    = { app = "kube-state-metrics" }
  }

  spec {
    replicas = 1
    selector { match_labels = { app = "kube-state-metrics" } }

    template {
      metadata {
        labels = { app = "kube-state-metrics" }
      }

      spec {
        service_account_name = kubernetes_service_account_v1.kube_state_metrics.metadata[0].name

        container {
          name  = "kube-state-metrics"
          image = "registry.k8s.io/kube-state-metrics/kube-state-metrics:v2.12.0"

          port {
            container_port = 8080
            name           = "metrics"
          }

          resources {
            limits = {
              memory = "256Mi"
              cpu    = "250m"
            }
            requests = {
              memory = "64Mi"
              cpu    = "50m"
            }
          }
        }
      }
    }
  }
}

resource "kubernetes_service_v1" "kube_state_metrics" {
  metadata {
    name      = "kube-state-metrics"
    namespace = kubernetes_namespace_v1.monitoring.metadata[0].name
    labels    = { app = "kube-state-metrics" }
  }

  spec {
    selector = { app = "kube-state-metrics" }
    port {
      port        = 8080
      target_port = "metrics"
      name        = "metrics"
    }
    type = "ClusterIP"
  }
}

resource "kubernetes_service_account_v1" "node_exporter" {
  metadata {
    name      = "node-exporter"
    namespace = kubernetes_namespace_v1.monitoring.metadata[0].name
  }
}

resource "kubernetes_daemon_set_v1" "node_exporter" {
  metadata {
    name      = "node-exporter"
    namespace = kubernetes_namespace_v1.monitoring.metadata[0].name
    labels    = { app = "node-exporter" }
  }

  lifecycle {
    ignore_changes = [
      metadata[0].annotations,
    ]
  }

  spec {
    selector { match_labels = { app = "node-exporter" } }

    template {
      metadata {
        labels = { app = "node-exporter" }
      }

      spec {
        service_account_name = kubernetes_service_account_v1.node_exporter.metadata[0].name
        host_pid             = true
        host_network         = true

        toleration {
          effect   = "NoSchedule"
          operator = "Exists"
        }

        volume {
          name = "proc"
          host_path {
            path = "/proc"
          }
        }

        volume {
          name = "sys"
          host_path {
            path = "/sys"
          }
        }

        volume {
          name = "root"
          host_path {
            path = "/"
          }
        }

        container {
          name  = "node-exporter"
          image = "prom/node-exporter:v1.8.0"
          args = [
            "--path.procfs=/host/proc",
            "--path.sysfs=/host/sys",
            "--path.rootfs=/host/root",
            "--collector.filesystem.ignored-mount-points=^/(sys|proc|dev|host|etc)($$|/)",
          ]

          port {
            container_port = 9100
            name           = "metrics"
            protocol       = "TCP"
          }

          security_context {
            run_as_user = 0
          }

          volume_mount {
            name       = "proc"
            mount_path = "/host/proc"
            read_only  = true
          }

          volume_mount {
            name       = "sys"
            mount_path = "/host/sys"
            read_only  = true
          }

          volume_mount {
            name              = "root"
            mount_path        = "/host/root"
            read_only         = true
            mount_propagation = "HostToContainer"
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
        }
      }
    }
  }
}

resource "kubernetes_service_v1" "node_exporter" {
  metadata {
    name      = "node-exporter"
    namespace = kubernetes_namespace_v1.monitoring.metadata[0].name
    labels    = { app = "node-exporter" }
  }

  spec {
    selector = { app = "node-exporter" }
    port {
      port        = 9100
      target_port = "metrics"
      name        = "metrics"
    }
    type = "ClusterIP"
  }
}

resource "kubernetes_service_account_v1" "cadvisor" {
  metadata {
    name      = "cadvisor"
    namespace = kubernetes_namespace_v1.monitoring.metadata[0].name
  }
}

resource "kubernetes_daemon_set_v1" "cadvisor" {
  metadata {
    name      = "cadvisor"
    namespace = kubernetes_namespace_v1.monitoring.metadata[0].name
    labels    = { app = "cadvisor" }
  }

  spec {
    selector { match_labels = { app = "cadvisor" } }

    template {
      metadata {
        labels = { app = "cadvisor" }
      }

      spec {
        service_account_name = kubernetes_service_account_v1.cadvisor.metadata[0].name
        host_pid             = true

        toleration {
          effect   = "NoSchedule"
          operator = "Exists"
        }

        volume {
          name = "rootfs"
          host_path {
            path = "/"
          }
        }

        volume {
          name = "sys"
          host_path {
            path = "/sys"
          }
        }

        volume {
          name = "containerd-sock"
          host_path {
            path = "/run/k3s/containerd/containerd.sock"
            type = "Socket"
          }
        }

        volume {
          name = "containerd-run"
          host_path {
            path = "/run/k3s/containerd"
          }
        }

        container {
          name  = "cadvisor"
          image = "gcr.io/cadvisor/cadvisor:v0.49.1"
          args = [
            "--housekeeping_interval=30s",
            "--docker_only=false",
            "--containerd=/run/containerd/containerd.sock",
            "--disable_metrics=percpu,cpuLoad,cpu_topology,cpuset,disk,diskIO,hugetlb,memory_numa,network,oom_event,perf_event,process,referenced_memory,resctrl,sched,tcp,udp,advtcp",
            "--listen_ip=0.0.0.0",
          ]

          port {
            container_port = 8080
            name           = "metrics"
            protocol       = "TCP"
          }

          security_context {
            privileged = true
          }

          volume_mount {
            name       = "rootfs"
            mount_path = "/rootfs"
            read_only  = true
          }

          volume_mount {
            name       = "sys"
            mount_path = "/sys"
            read_only  = true
          }

          volume_mount {
            name       = "containerd-sock"
            mount_path = "/run/containerd/containerd.sock"
            read_only  = true
          }

          volume_mount {
            name       = "containerd-run"
            mount_path = "/run/containerd"
            read_only  = true
          }

          resources {
            limits = {
              memory = "2Gi"
              cpu    = "500m"
            }
            requests = {
              memory = "256Mi"
              cpu    = "100m"
            }
          }
        }
      }
    }
  }
}

resource "kubernetes_service_v1" "cadvisor" {
  metadata {
    name      = "cadvisor"
    namespace = kubernetes_namespace_v1.monitoring.metadata[0].name
    labels    = { app = "cadvisor" }
  }

  spec {
    selector = { app = "cadvisor" }
    port {
      port        = 8080
      target_port = "metrics"
      name        = "metrics"
    }
    type = "ClusterIP"
  }
}
