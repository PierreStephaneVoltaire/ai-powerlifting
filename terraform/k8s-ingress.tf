resource "kubectl_manifest" "snippets_gateway_global" {
  depends_on = [
    null_resource.ngf_snippets_enable,
    kubernetes_deployment.tinyauth,
  ]

  yaml_body = <<-YAML
apiVersion: gateway.nginx.org/v1alpha1
kind: SnippetsFilter
metadata:
  name: gateway-global-setup
  namespace: ${kubernetes_namespace.if_portals.metadata[0].name}
spec:
  snippets:
    - context: http
      value: |
        client_max_body_size 500M;
        limit_req_zone $binary_remote_addr zone=portal_limit:10m rate=30r/s;
    - context: http.server
      value: |
        location = /_tinyauth {
            internal;
            proxy_pass http://tinyauth.${kubernetes_namespace.if_portals.metadata[0].name}.svc.cluster.local:3000/api/auth/nginx;
            proxy_set_header x-forwarded-proto $scheme;
            proxy_set_header x-forwarded-host $http_host;
            proxy_set_header x-forwarded-uri $request_uri;
            proxy_set_header Content-Length "";
            proxy_set_header Connection "";
            proxy_pass_request_body off;
        }
    - context: http.server.location
      value: |
        add_header X-Frame-Options "SAMEORIGIN" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header Referrer-Policy "strict-origin-when-cross-origin" always;
        add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
        limit_req zone=portal_limit burst=20 nodelay;
  YAML
}

resource "kubectl_manifest" "snippets_auth_and_security" {
  depends_on = [kubectl_manifest.snippets_gateway_global]

  yaml_body = <<-YAML
apiVersion: gateway.nginx.org/v1alpha1
kind: SnippetsFilter
metadata:
  name: auth-and-security
  namespace: ${kubernetes_namespace.if_portals.metadata[0].name}
spec:
  snippets:
    - context: http.server.location
      value: |
        auth_request /_tinyauth;
        client_max_body_size 500M;
        error_page 401 =302 /auth/?rd=$scheme://$http_host$request_uri;
        add_header X-Frame-Options "SAMEORIGIN" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header Referrer-Policy "strict-origin-when-cross-origin" always;
        add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
        add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://static.cloudflareinsights.com; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https://powerlifting-session-videos.s3.ca-central-1.amazonaws.com; font-src 'self' data:; connect-src 'self' https://cloudflareinsights.com; media-src 'self' https://powerlifting-session-videos.s3.ca-central-1.amazonaws.com; frame-ancestors 'self';" always;
        limit_req zone=portal_limit burst=20 nodelay;
  YAML
}

resource "kubectl_manifest" "snippets_security_only" {
  depends_on = [null_resource.ngf_snippets_enable]

  yaml_body = <<-YAML
apiVersion: gateway.nginx.org/v1alpha1
kind: SnippetsFilter
metadata:
  name: security-only
  namespace: ${kubernetes_namespace.if_portals.metadata[0].name}
spec:
  snippets:
    - context: http.server.location
      value: |
        proxy_read_timeout 300s;
        client_max_body_size 500M;
        add_header X-Frame-Options "SAMEORIGIN" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header Referrer-Policy "strict-origin-when-cross-origin" always;
        add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
        add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://static.cloudflareinsights.com; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https://powerlifting-session-videos.s3.ca-central-1.amazonaws.com https://cdn.discordapp.com; font-src 'self' data:; connect-src 'self' https://cloudflareinsights.com; media-src 'self' https://powerlifting-session-videos.s3.ca-central-1.amazonaws.com; frame-ancestors 'self';" always;
        limit_req zone=portal_limit burst=20 nodelay;
  YAML
}

resource "kubectl_manifest" "snippets_terminal" {
  depends_on = [null_resource.ngf_snippets_enable]

  yaml_body = <<-YAML
apiVersion: gateway.nginx.org/v1alpha1
kind: SnippetsFilter
metadata:
  name: terminal
  namespace: ${kubernetes_namespace.if_portals.metadata[0].name}
spec:
  snippets:
    - context: http.server.location
      value: |
        add_header X-Frame-Options "SAMEORIGIN" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header Referrer-Policy "strict-origin-when-cross-origin" always;
        add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
        add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://static.cloudflareinsights.com; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: blob: https://fastapi.tiangolo.com; font-src 'self' data:; connect-src 'self' https://cloudflareinsights.com; media-src 'self'; frame-ancestors 'self';" always;
        limit_req zone=portal_limit burst=20 nodelay;
  YAML
}

resource "kubectl_manifest" "route_tinyauth" {
  depends_on = [kubectl_manifest.snippets_gateway_global]

  yaml_body = <<-YAML
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: tinyauth-portal
  namespace: ${kubernetes_namespace.if_portals.metadata[0].name}
spec:
  parentRefs:
    - name: ${var.gateway_name}
      namespace: ${var.gateway_namespace}
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /auth
      filters:
        - type: ExtensionRef
          extensionRef:
            group: gateway.nginx.org
            kind: SnippetsFilter
            name: gateway-global-setup
        - type: URLRewrite
          urlRewrite:
            path:
              type: ReplacePrefixMatch
              replacePrefixMatch: /
      backendRefs:
        - name: ${kubernetes_service.tinyauth.metadata[0].name}
          port: 3000
  YAML
}

resource "kubectl_manifest" "route_protected_frontends" {
  depends_on = [kubectl_manifest.snippets_auth_and_security]

  yaml_body = <<-YAML
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: protected-frontends
  namespace: ${kubernetes_namespace.if_portals.metadata[0].name}
spec:
  parentRefs:
    - name: ${var.gateway_name}
      namespace: ${var.gateway_namespace}
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /app/main
      filters:
        - type: ExtensionRef
          extensionRef:
            group: gateway.nginx.org
            kind: SnippetsFilter
            name: auth-and-security
        - type: URLRewrite
          urlRewrite:
            path:
              type: ReplacePrefixMatch
              replacePrefixMatch: /
      backendRefs:
        - name: ${kubernetes_service.portal_frontends["main-portal"].metadata[0].name}
          port: 3001
    - matches:
        - path:
            type: PathPrefix
            value: /app/finance
      filters:
        - type: ExtensionRef
          extensionRef:
            group: gateway.nginx.org
            kind: SnippetsFilter
            name: auth-and-security
        - type: URLRewrite
          urlRewrite:
            path:
              type: ReplacePrefixMatch
              replacePrefixMatch: /
      backendRefs:
        - name: ${kubernetes_service.portal_frontends["finance-portal"].metadata[0].name}
          port: 3001
    - matches:
        - path:
            type: PathPrefix
            value: /app/diary
      filters:
        - type: ExtensionRef
          extensionRef:
            group: gateway.nginx.org
            kind: SnippetsFilter
            name: auth-and-security
        - type: URLRewrite
          urlRewrite:
            path:
              type: ReplacePrefixMatch
              replacePrefixMatch: /
      backendRefs:
        - name: ${kubernetes_service.portal_frontends["diary-portal"].metadata[0].name}
          port: 3001
    - matches:
        - path:
            type: PathPrefix
            value: /app/proposals
      filters:
        - type: ExtensionRef
          extensionRef:
            group: gateway.nginx.org
            kind: SnippetsFilter
            name: auth-and-security
        - type: URLRewrite
          urlRewrite:
            path:
              type: ReplacePrefixMatch
              replacePrefixMatch: /
      backendRefs:
        - name: ${kubernetes_service.portal_frontends["proposals-portal"].metadata[0].name}
          port: 3001
  YAML
}

resource "kubectl_manifest" "route_protected_backends" {
  depends_on = [kubectl_manifest.snippets_auth_and_security]

  yaml_body = <<-YAML
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: protected-backends
  namespace: ${kubernetes_namespace.if_portals.metadata[0].name}
spec:
  parentRefs:
    - name: ${var.gateway_name}
      namespace: ${var.gateway_namespace}
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /app/main
      filters:
        - type: ExtensionRef
          extensionRef:
            group: gateway.nginx.org
            kind: SnippetsFilter
            name: auth-and-security
        - type: URLRewrite
          urlRewrite:
            path:
              type: ReplacePrefixMatch
              replacePrefixMatch: /
      backendRefs:
        - name: ${kubernetes_service.portal_backends["main-portal"].metadata[0].name}
          port: 3000
    - matches:
        - path:
            type: PathPrefix
            value: /finance
      filters:
        - type: ExtensionRef
          extensionRef:
            group: gateway.nginx.org
            kind: SnippetsFilter
            name: auth-and-security
        - type: URLRewrite
          urlRewrite:
            path:
              type: ReplacePrefixMatch
              replacePrefixMatch: /
      backendRefs:
        - name: ${kubernetes_service.portal_backends["finance-portal"].metadata[0].name}
          port: 3002
    - matches:
        - path:
            type: PathPrefix
            value: /diary
      filters:
        - type: ExtensionRef
          extensionRef:
            group: gateway.nginx.org
            kind: SnippetsFilter
            name: auth-and-security
        - type: URLRewrite
          urlRewrite:
            path:
              type: ReplacePrefixMatch
              replacePrefixMatch: /
      backendRefs:
        - name: ${kubernetes_service.portal_backends["diary-portal"].metadata[0].name}
          port: 3003
    - matches:
        - path:
            type: PathPrefix
            value: /proposals
      filters:
        - type: ExtensionRef
          extensionRef:
            group: gateway.nginx.org
            kind: SnippetsFilter
            name: auth-and-security
        - type: URLRewrite
          urlRewrite:
            path:
              type: ReplacePrefixMatch
              replacePrefixMatch: /
      backendRefs:
        - name: ${kubernetes_service.portal_backends["proposals-portal"].metadata[0].name}
          port: 3004
  YAML
}

resource "kubectl_manifest" "route_public" {
  depends_on = [kubectl_manifest.snippets_security_only]

  yaml_body = <<-YAML
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: public-routes
  namespace: ${kubernetes_namespace.if_portals.metadata[0].name}
spec:
  parentRefs:
    - name: ${var.gateway_name}
      namespace: ${var.gateway_namespace}
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /agent
      filters:
        - type: ExtensionRef
          extensionRef:
            group: gateway.nginx.org
            kind: SnippetsFilter
            name: security-only
        - type: URLRewrite
          urlRewrite:
            path:
              type: ReplacePrefixMatch
              replacePrefixMatch: /
      backendRefs:
        - name: ${kubernetes_service.if_agent_api.metadata[0].name}
          port: 8000
  YAML
}

resource "kubectl_manifest" "route_grafana" {
  depends_on = [
    kubectl_manifest.snippets_auth_and_security,
    kubectl_manifest.monitoring_reference_grant,
  ]

  yaml_body = <<-YAML
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: grafana
  namespace: ${kubernetes_namespace.if_portals.metadata[0].name}
spec:
  parentRefs:
    - name: ${var.gateway_name}
      namespace: ${var.gateway_namespace}
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /grafana
      filters:
        - type: ExtensionRef
          extensionRef:
            group: gateway.nginx.org
            kind: SnippetsFilter
            name: auth-and-security
        - type: URLRewrite
          urlRewrite:
            path:
              type: ReplacePrefixMatch
              replacePrefixMatch: /
      backendRefs:
        - name: grafana
          namespace: ${kubernetes_namespace.monitoring.metadata[0].name}
          port: 3000
  YAML
}

# ─── Per-domain HTTPRoutes (one per utils/*/domain.yaml with a domain field) ──
# Each app with a domain.yaml gets its own subdomain route through the tunnel.
# Auth is handled at the Cloudflare edge; only the security-only snippet applies here.

resource "kubectl_manifest" "route_per_domain" {
  for_each = local.public_apps

  depends_on = [kubectl_manifest.snippets_security_only]

  yaml_body = <<-YAML
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: domain-${each.key}
  namespace: ${kubernetes_namespace.if_portals.metadata[0].name}
spec:
  parentRefs:
    - name: ${var.gateway_name}
      namespace: ${var.gateway_namespace}
  hostnames:
    - ${each.value.domain}
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /api
      filters:
        - type: ExtensionRef
          extensionRef:
            group: gateway.nginx.org
            kind: SnippetsFilter
            name: security-only
      backendRefs:
        - name: ${each.key}-backend
          port: ${local.portal_backend_ports[each.key]}
    - matches:
        - path:
            type: PathPrefix
            value: /
      filters:
        - type: ExtensionRef
          extensionRef:
            group: gateway.nginx.org
            kind: SnippetsFilter
            name: security-only
      backendRefs:
        - name: ${each.key}-frontend
          port: 3001
  YAML
}
