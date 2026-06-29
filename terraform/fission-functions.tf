resource "kubectl_manifest" "pl_fission_env" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Environment
metadata:
  name: pl-fission-tools
  namespace: fission
spec:
  version: 3
  keeparchive: false
  runtime:
    image: ghcr.io/fission/python-env
  builder:
    image: ghcr.io/fission/python-builder
  terminationGracePeriod: 120
  resources:
    requests:
      cpu: 100m
      memory: 128Mi
    limits:
      cpu: 1000m
      memory: 512Mi
YAML
}

resource "kubectl_manifest" "pl_pkg_analysis_section" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-analysis_section
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: analysis_section.zip
YAML
}

resource "kubectl_manifest" "pl_fn_analysis_section" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-analysis_section
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-analysis_section
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-analysis_section
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "analysis_section"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 512Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_analysis_section" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-analysis_section
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-analysis_section
  methods:
    - POST
  relativeurl: /analysis_section
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_analyze_powerlifting_stats" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-analyze_powerlifting_stats
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: analyze_powerlifting_stats.zip
YAML
}

resource "kubectl_manifest" "pl_fn_analyze_powerlifting_stats" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-analyze_powerlifting_stats
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-analyze_powerlifting_stats
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 2
            SpecializationTimeout: 120
            TargetCPUPercent: 80
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-analyze_powerlifting_stats
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: POWERLIFTING_S3_BUCKET
              value: "${var.powerlifting_s3_bucket}"
            - name: IF_TOOL_NAME
              value: "analyze_powerlifting_stats"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 512Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_analyze_powerlifting_stats" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-analyze_powerlifting_stats
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-analyze_powerlifting_stats
  methods:
    - POST
  relativeurl: /analyze_powerlifting_stats
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_analyze_progression" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-analyze_progression
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: analyze_progression.zip
YAML
}

resource "kubectl_manifest" "pl_fn_analyze_progression" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-analyze_progression
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-analyze_progression
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 2
            SpecializationTimeout: 120
            TargetCPUPercent: 80
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-analyze_progression
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "analyze_progression"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 512Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_analyze_progression" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-analyze_progression
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-analyze_progression
  methods:
    - POST
  relativeurl: /analyze_progression
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_analyze_rpe_drift" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-analyze_rpe_drift
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: analyze_rpe_drift.zip
YAML
}

resource "kubectl_manifest" "pl_fn_analyze_rpe_drift" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-analyze_rpe_drift
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-analyze_rpe_drift
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 2
            SpecializationTimeout: 120
            TargetCPUPercent: 80
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-analyze_rpe_drift
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "analyze_rpe_drift"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 512Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_analyze_rpe_drift" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-analyze_rpe_drift
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-analyze_rpe_drift
  methods:
    - POST
  relativeurl: /analyze_rpe_drift
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_block_correlation_analysis" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-block_correlation_analysis
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: block_correlation_analysis.zip
YAML
}

resource "kubectl_manifest" "pl_fn_block_correlation_analysis" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-block_correlation_analysis
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-block_correlation_analysis
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-block_correlation_analysis
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "block_correlation_analysis"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 512Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_block_correlation_analysis" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-block_correlation_analysis
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-block_correlation_analysis
  methods:
    - POST
  relativeurl: /block_correlation_analysis
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_block_program_evaluation" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-block_program_evaluation
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: block_program_evaluation.zip
YAML
}

resource "kubectl_manifest" "pl_fn_block_program_evaluation" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-block_program_evaluation
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-block_program_evaluation
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 1
            SpecializationTimeout: 120
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-block_program_evaluation
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: ANALYSIS_MODEL
              value: "anthropic/claude-sonnet-4.6"
            - name: ESTIMATE_MODEL
              value: "anthropic/claude-sonnet-4.6"
            - name: IMPORT_FAST_MODEL
              value: "anthropic/claude-haiku-4.5"
            - name: GLOSSARY_TEXT_MODEL
              value: "google/gemini-3.1-flash-lite"
            - name: IF_TOOL_NAME
              value: "block_program_evaluation"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 512Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_block_program_evaluation" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-block_program_evaluation
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-block_program_evaluation
  methods:
    - POST
  relativeurl: /block_program_evaluation
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_budget_advisor" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-budget_advisor
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: budget_advisor.zip
YAML
}

resource "kubectl_manifest" "pl_fn_budget_advisor" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-budget_advisor
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-budget_advisor
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 1
            SpecializationTimeout: 120
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-budget_advisor
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: ANALYSIS_MODEL
              value: "anthropic/claude-sonnet-4.6"
            - name: ESTIMATE_MODEL
              value: "anthropic/claude-sonnet-4.6"
            - name: IMPORT_FAST_MODEL
              value: "anthropic/claude-haiku-4.5"
            - name: GLOSSARY_TEXT_MODEL
              value: "google/gemini-3.1-flash-lite"
            - name: IF_TOOL_NAME
              value: "budget_advisor"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 512Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_budget_advisor" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-budget_advisor
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-budget_advisor
  methods:
    - POST
  relativeurl: /budget_advisor
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_budget_priority_timeline" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-budget_priority_timeline
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: budget_priority_timeline.zip
YAML
}

resource "kubectl_manifest" "pl_fn_budget_priority_timeline" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-budget_priority_timeline
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-budget_priority_timeline
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 1
            SpecializationTimeout: 120
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-budget_priority_timeline
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: ANALYSIS_MODEL
              value: "anthropic/claude-sonnet-4.6"
            - name: ESTIMATE_MODEL
              value: "anthropic/claude-sonnet-4.6"
            - name: IMPORT_FAST_MODEL
              value: "anthropic/claude-haiku-4.5"
            - name: GLOSSARY_TEXT_MODEL
              value: "google/gemini-3.1-flash-lite"
            - name: IF_TOOL_NAME
              value: "budget_priority_timeline"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 512Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_budget_priority_timeline" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-budget_priority_timeline
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-budget_priority_timeline
  methods:
    - POST
  relativeurl: /budget_priority_timeline
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_calculate_attempts" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-calculate_attempts
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: calculate_attempts.zip
YAML
}

resource "kubectl_manifest" "pl_fn_calculate_attempts" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-calculate_attempts
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-calculate_attempts
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-calculate_attempts
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "calculate_attempts"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_calculate_attempts" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-calculate_attempts
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-calculate_attempts
  methods:
    - POST
  relativeurl: /calculate_attempts
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_calculate_dots" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-calculate_dots
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: calculate_dots.zip
YAML
}

resource "kubectl_manifest" "pl_fn_calculate_dots" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-calculate_dots
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-calculate_dots
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-calculate_dots
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "calculate_dots"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 128Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_calculate_dots" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-calculate_dots
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-calculate_dots
  methods:
    - POST
  relativeurl: /calculate_dots
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_correlation_analysis" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-correlation_analysis
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: correlation_analysis.zip
YAML
}

resource "kubectl_manifest" "pl_fn_correlation_analysis" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-correlation_analysis
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-correlation_analysis
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 1
            SpecializationTimeout: 120
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-correlation_analysis
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: ANALYSIS_MODEL
              value: "anthropic/claude-sonnet-4.6"
            - name: ESTIMATE_MODEL
              value: "anthropic/claude-sonnet-4.6"
            - name: IMPORT_FAST_MODEL
              value: "anthropic/claude-haiku-4.5"
            - name: GLOSSARY_TEXT_MODEL
              value: "google/gemini-3.1-flash-lite"
            - name: IF_TOOL_NAME
              value: "correlation_analysis"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 512Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_correlation_analysis" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-correlation_analysis
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-correlation_analysis
  methods:
    - POST
  relativeurl: /correlation_analysis
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_days_until" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-days_until
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: days_until.zip
YAML
}

resource "kubectl_manifest" "pl_fn_days_until" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-days_until
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-days_until
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-days_until
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "days_until"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 128Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_days_until" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-days_until
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-days_until
  methods:
    - POST
  relativeurl: /days_until
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_estimate_1rm" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-estimate_1rm
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: estimate_1rm.zip
YAML
}

resource "kubectl_manifest" "pl_fn_estimate_1rm" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-estimate_1rm
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-estimate_1rm
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-estimate_1rm
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "estimate_1rm"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 128Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_estimate_1rm" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-estimate_1rm
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-estimate_1rm
  methods:
    - POST
  relativeurl: /estimate_1rm
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_export_program_history" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-export_program_history
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: export_program_history.zip
YAML
}

resource "kubectl_manifest" "pl_fn_export_program_history" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-export_program_history
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-export_program_history
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-export_program_history
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "export_program_history"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 512Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_export_program_history" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-export_program_history
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-export_program_history
  methods:
    - POST
  relativeurl: /export_program_history
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_export_program_markdown" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-export_program_markdown
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: export_program_markdown.zip
YAML
}

resource "kubectl_manifest" "pl_fn_export_program_markdown" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-export_program_markdown
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-export_program_markdown
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-export_program_markdown
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "export_program_markdown"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 512Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_export_program_markdown" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-export_program_markdown
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-export_program_markdown
  methods:
    - POST
  relativeurl: /export_program_markdown
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_fatigue_profile_estimate" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-fatigue_profile_estimate
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: fatigue_profile_estimate.zip
YAML
}

resource "kubectl_manifest" "pl_fn_fatigue_profile_estimate" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-fatigue_profile_estimate
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-fatigue_profile_estimate
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 1
            SpecializationTimeout: 120
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-fatigue_profile_estimate
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: ANALYSIS_MODEL
              value: "anthropic/claude-sonnet-4.6"
            - name: ESTIMATE_MODEL
              value: "anthropic/claude-sonnet-4.6"
            - name: IMPORT_FAST_MODEL
              value: "anthropic/claude-haiku-4.5"
            - name: GLOSSARY_TEXT_MODEL
              value: "google/gemini-3.1-flash-lite"
            - name: IF_TOOL_NAME
              value: "fatigue_profile_estimate"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 512Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_fatigue_profile_estimate" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-fatigue_profile_estimate
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-fatigue_profile_estimate
  methods:
    - POST
  relativeurl: /fatigue_profile_estimate
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_get_analysis_markdown" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-get_analysis_markdown
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: get_analysis_markdown.zip
YAML
}

resource "kubectl_manifest" "pl_fn_get_analysis_markdown" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-get_analysis_markdown
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-get_analysis_markdown
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 1
            MaxScale: 2
            SpecializationTimeout: 60
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-get_analysis_markdown
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "get_analysis_markdown"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 512Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_get_analysis_markdown" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-get_analysis_markdown
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-get_analysis_markdown
  methods:
    - POST
  relativeurl: /get_analysis_markdown
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_glossary_add" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-glossary_add
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: glossary_add.zip
YAML
}

resource "kubectl_manifest" "pl_fn_glossary_add" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-glossary_add
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-glossary_add
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-glossary_add
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "glossary_add"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_glossary_add" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-glossary_add
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-glossary_add
  methods:
    - POST
  relativeurl: /glossary_add
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_glossary_estimate_e1rm" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-glossary_estimate_e1rm
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: glossary_estimate_e1rm.zip
YAML
}

resource "kubectl_manifest" "pl_fn_glossary_estimate_e1rm" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-glossary_estimate_e1rm
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-glossary_estimate_e1rm
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 1
            SpecializationTimeout: 120
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-glossary_estimate_e1rm
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: ANALYSIS_MODEL
              value: "anthropic/claude-sonnet-4.6"
            - name: ESTIMATE_MODEL
              value: "anthropic/claude-sonnet-4.6"
            - name: IMPORT_FAST_MODEL
              value: "anthropic/claude-haiku-4.5"
            - name: GLOSSARY_TEXT_MODEL
              value: "google/gemini-3.1-flash-lite"
            - name: IF_TOOL_NAME
              value: "glossary_estimate_e1rm"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 512Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_glossary_estimate_e1rm" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-glossary_estimate_e1rm
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-glossary_estimate_e1rm
  methods:
    - POST
  relativeurl: /glossary_estimate_e1rm
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_glossary_estimate_fatigue" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-glossary_estimate_fatigue
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: glossary_estimate_fatigue.zip
YAML
}

resource "kubectl_manifest" "pl_fn_glossary_estimate_fatigue" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-glossary_estimate_fatigue
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-glossary_estimate_fatigue
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 1
            SpecializationTimeout: 120
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-glossary_estimate_fatigue
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: ANALYSIS_MODEL
              value: "anthropic/claude-sonnet-4.6"
            - name: ESTIMATE_MODEL
              value: "anthropic/claude-sonnet-4.6"
            - name: IMPORT_FAST_MODEL
              value: "anthropic/claude-haiku-4.5"
            - name: GLOSSARY_TEXT_MODEL
              value: "google/gemini-3.1-flash-lite"
            - name: IF_TOOL_NAME
              value: "glossary_estimate_fatigue"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 512Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_glossary_estimate_fatigue" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-glossary_estimate_fatigue
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-glossary_estimate_fatigue
  methods:
    - POST
  relativeurl: /glossary_estimate_fatigue
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_glossary_estimate_muscles" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-glossary_estimate_muscles
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: glossary_estimate_muscles.zip
YAML
}

resource "kubectl_manifest" "pl_fn_glossary_estimate_muscles" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-glossary_estimate_muscles
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-glossary_estimate_muscles
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-glossary_estimate_muscles
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "glossary_estimate_muscles"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 512Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_glossary_estimate_muscles" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-glossary_estimate_muscles
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-glossary_estimate_muscles
  methods:
    - POST
  relativeurl: /glossary_estimate_muscles
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_glossary_generate_text" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-glossary_generate_text
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: glossary_generate_text.zip
YAML
}

resource "kubectl_manifest" "pl_fn_glossary_generate_text" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-glossary_generate_text
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-glossary_generate_text
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 1
            SpecializationTimeout: 120
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-glossary_generate_text
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: ANALYSIS_MODEL
              value: "anthropic/claude-sonnet-4.6"
            - name: ESTIMATE_MODEL
              value: "anthropic/claude-sonnet-4.6"
            - name: IMPORT_FAST_MODEL
              value: "anthropic/claude-haiku-4.5"
            - name: GLOSSARY_TEXT_MODEL
              value: "google/gemini-3.1-flash-lite"
            - name: IF_TOOL_NAME
              value: "glossary_generate_text"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 512Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_glossary_generate_text" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-glossary_generate_text
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-glossary_generate_text
  methods:
    - POST
  relativeurl: /glossary_generate_text
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_glossary_set_e1rm" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-glossary_set_e1rm
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: glossary_set_e1rm.zip
YAML
}

resource "kubectl_manifest" "pl_fn_glossary_set_e1rm" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-glossary_set_e1rm
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-glossary_set_e1rm
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-glossary_set_e1rm
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "glossary_set_e1rm"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_glossary_set_e1rm" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-glossary_set_e1rm
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-glossary_set_e1rm
  methods:
    - POST
  relativeurl: /glossary_set_e1rm
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_glossary_update" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-glossary_update
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: glossary_update.zip
YAML
}

resource "kubectl_manifest" "pl_fn_glossary_update" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-glossary_update
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-glossary_update
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-glossary_update
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "glossary_update"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_glossary_update" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-glossary_update
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-glossary_update
  methods:
    - POST
  relativeurl: /glossary_update
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_health_add_exercise" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-health_add_exercise
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: health_add_exercise.zip
YAML
}

resource "kubectl_manifest" "pl_fn_health_add_exercise" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-health_add_exercise
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-health_add_exercise
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-health_add_exercise
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "health_add_exercise"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_health_add_exercise" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-health_add_exercise
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-health_add_exercise
  methods:
    - POST
  relativeurl: /health_add_exercise
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_health_complete_competition" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-health_complete_competition
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: health_complete_competition.zip
YAML
}

resource "kubectl_manifest" "pl_fn_health_complete_competition" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-health_complete_competition
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-health_complete_competition
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-health_complete_competition
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "health_complete_competition"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_health_complete_competition" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-health_complete_competition
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-health_complete_competition
  methods:
    - POST
  relativeurl: /health_complete_competition
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_health_create_competition" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-health_create_competition
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: health_create_competition.zip
YAML
}

resource "kubectl_manifest" "pl_fn_health_create_competition" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-health_create_competition
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-health_create_competition
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-health_create_competition
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "health_create_competition"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_health_create_competition" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-health_create_competition
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-health_create_competition
  methods:
    - POST
  relativeurl: /health_create_competition
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_health_create_session" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-health_create_session
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: health_create_session.zip
YAML
}

resource "kubectl_manifest" "pl_fn_health_create_session" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-health_create_session
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-health_create_session
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-health_create_session
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "health_create_session"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_health_create_session" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-health_create_session
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-health_create_session
  methods:
    - POST
  relativeurl: /health_create_session
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_health_delete_competition" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-health_delete_competition
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: health_delete_competition.zip
YAML
}

resource "kubectl_manifest" "pl_fn_health_delete_competition" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-health_delete_competition
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-health_delete_competition
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-health_delete_competition
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "health_delete_competition"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_health_delete_competition" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-health_delete_competition
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-health_delete_competition
  methods:
    - POST
  relativeurl: /health_delete_competition
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_health_delete_diet_note" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-health_delete_diet_note
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: health_delete_diet_note.zip
YAML
}

resource "kubectl_manifest" "pl_fn_health_delete_diet_note" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-health_delete_diet_note
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-health_delete_diet_note
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-health_delete_diet_note
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "health_delete_diet_note"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_health_delete_diet_note" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-health_delete_diet_note
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-health_delete_diet_note
  methods:
    - POST
  relativeurl: /health_delete_diet_note
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_health_delete_session" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-health_delete_session
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: health_delete_session.zip
YAML
}

resource "kubectl_manifest" "pl_fn_health_delete_session" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-health_delete_session
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-health_delete_session
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-health_delete_session
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "health_delete_session"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_health_delete_session" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-health_delete_session
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-health_delete_session
  methods:
    - POST
  relativeurl: /health_delete_session
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_health_get_competition" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-health_get_competition
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: health_get_competition.zip
YAML
}

resource "kubectl_manifest" "pl_fn_health_get_competition" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-health_get_competition
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-health_get_competition
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-health_get_competition
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "health_get_competition"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_health_get_competition" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-health_get_competition
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-health_get_competition
  methods:
    - POST
  relativeurl: /health_get_competition
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_health_get_current_maxes" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-health_get_current_maxes
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: health_get_current_maxes.zip
YAML
}

resource "kubectl_manifest" "pl_fn_health_get_current_maxes" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-health_get_current_maxes
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-health_get_current_maxes
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 1
            MaxScale: 2
            SpecializationTimeout: 60
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-health_get_current_maxes
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "health_get_current_maxes"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_health_get_current_maxes" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-health_get_current_maxes
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-health_get_current_maxes
  methods:
    - POST
  relativeurl: /health_get_current_maxes
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_health_get_diet_notes" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-health_get_diet_notes
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: health_get_diet_notes.zip
YAML
}

resource "kubectl_manifest" "pl_fn_health_get_diet_notes" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-health_get_diet_notes
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-health_get_diet_notes
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-health_get_diet_notes
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "health_get_diet_notes"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_health_get_diet_notes" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-health_get_diet_notes
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-health_get_diet_notes
  methods:
    - POST
  relativeurl: /health_get_diet_notes
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_health_get_federation_library" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-health_get_federation_library
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: health_get_federation_library.zip
YAML
}

resource "kubectl_manifest" "pl_fn_health_get_federation_library" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-health_get_federation_library
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-health_get_federation_library
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-health_get_federation_library
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "health_get_federation_library"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_health_get_federation_library" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-health_get_federation_library
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-health_get_federation_library
  methods:
    - POST
  relativeurl: /health_get_federation_library
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_health_get_goals" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-health_get_goals
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: health_get_goals.zip
YAML
}

resource "kubectl_manifest" "pl_fn_health_get_goals" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-health_get_goals
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-health_get_goals
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 1
            MaxScale: 2
            SpecializationTimeout: 60
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-health_get_goals
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "health_get_goals"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_health_get_goals" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-health_get_goals
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-health_get_goals
  methods:
    - POST
  relativeurl: /health_get_goals
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_health_get_meta" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-health_get_meta
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: health_get_meta.zip
YAML
}

resource "kubectl_manifest" "pl_fn_health_get_meta" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-health_get_meta
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-health_get_meta
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 1
            MaxScale: 2
            SpecializationTimeout: 60
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-health_get_meta
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "health_get_meta"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_health_get_meta" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-health_get_meta
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-health_get_meta
  methods:
    - POST
  relativeurl: /health_get_meta
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_health_get_phases" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-health_get_phases
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: health_get_phases.zip
YAML
}

resource "kubectl_manifest" "pl_fn_health_get_phases" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-health_get_phases
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-health_get_phases
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 1
            MaxScale: 2
            SpecializationTimeout: 60
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-health_get_phases
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "health_get_phases"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_health_get_phases" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-health_get_phases
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-health_get_phases
  methods:
    - POST
  relativeurl: /health_get_phases
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_health_get_program" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-health_get_program
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: health_get_program.zip
YAML
}

resource "kubectl_manifest" "pl_fn_health_get_program" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-health_get_program
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-health_get_program
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 1
            MaxScale: 2
            SpecializationTimeout: 60
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-health_get_program
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "health_get_program"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_health_get_program" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-health_get_program
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-health_get_program
  methods:
    - POST
  relativeurl: /health_get_program
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_health_get_session" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-health_get_session
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: health_get_session.zip
YAML
}

resource "kubectl_manifest" "pl_fn_health_get_session" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-health_get_session
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-health_get_session
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 1
            MaxScale: 2
            SpecializationTimeout: 60
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-health_get_session
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "health_get_session"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_health_get_session" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-health_get_session
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-health_get_session
  methods:
    - POST
  relativeurl: /health_get_session
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_health_get_sessions_range" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-health_get_sessions_range
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: health_get_sessions_range.zip
YAML
}

resource "kubectl_manifest" "pl_fn_health_get_sessions_range" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-health_get_sessions_range
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-health_get_sessions_range
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 1
            MaxScale: 2
            SpecializationTimeout: 60
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-health_get_sessions_range
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "health_get_sessions_range"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_health_get_sessions_range" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-health_get_sessions_range
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-health_get_sessions_range
  methods:
    - POST
  relativeurl: /health_get_sessions_range
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_health_get_supplements" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-health_get_supplements
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: health_get_supplements.zip
YAML
}

resource "kubectl_manifest" "pl_fn_health_get_supplements" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-health_get_supplements
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-health_get_supplements
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-health_get_supplements
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "health_get_supplements"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_health_get_supplements" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-health_get_supplements
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-health_get_supplements
  methods:
    - POST
  relativeurl: /health_get_supplements
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_health_invalidate_program_cache" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-health_invalidate_program_cache
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: health_invalidate_program_cache.zip
YAML
}

resource "kubectl_manifest" "pl_fn_health_invalidate_program_cache" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-health_invalidate_program_cache
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-health_invalidate_program_cache
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-health_invalidate_program_cache
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "health_invalidate_program_cache"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_health_invalidate_program_cache" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-health_invalidate_program_cache
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-health_invalidate_program_cache
  methods:
    - POST
  relativeurl: /health_invalidate_program_cache
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_health_new_version" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-health_new_version
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: health_new_version.zip
YAML
}

resource "kubectl_manifest" "pl_fn_health_new_version" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-health_new_version
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-health_new_version
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-health_new_version
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "health_new_version"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_health_new_version" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-health_new_version
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-health_new_version
  methods:
    - POST
  relativeurl: /health_new_version
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_health_remove_exercise" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-health_remove_exercise
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: health_remove_exercise.zip
YAML
}

resource "kubectl_manifest" "pl_fn_health_remove_exercise" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-health_remove_exercise
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-health_remove_exercise
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-health_remove_exercise
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "health_remove_exercise"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_health_remove_exercise" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-health_remove_exercise
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-health_remove_exercise
  methods:
    - POST
  relativeurl: /health_remove_exercise
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_health_reschedule_session" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-health_reschedule_session
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: health_reschedule_session.zip
YAML
}

resource "kubectl_manifest" "pl_fn_health_reschedule_session" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-health_reschedule_session
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-health_reschedule_session
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-health_reschedule_session
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "health_reschedule_session"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_health_reschedule_session" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-health_reschedule_session
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-health_reschedule_session
  methods:
    - POST
  relativeurl: /health_reschedule_session
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_health_setup_initialize" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-health_setup_initialize
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: health_setup_initialize.zip
YAML
}

resource "kubectl_manifest" "pl_fn_health_setup_initialize" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-health_setup_initialize
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-health_setup_initialize
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-health_setup_initialize
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "health_setup_initialize"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 512Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_health_setup_initialize" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-health_setup_initialize
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-health_setup_initialize
  methods:
    - POST
  relativeurl: /health_setup_initialize
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_health_setup_status" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-health_setup_status
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: health_setup_status.zip
YAML
}

resource "kubectl_manifest" "pl_fn_health_setup_status" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-health_setup_status
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-health_setup_status
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-health_setup_status
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "health_setup_status"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_health_setup_status" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-health_setup_status
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-health_setup_status
  methods:
    - POST
  relativeurl: /health_setup_status
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_health_snapshot_competition_projection" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-health_snapshot_competition_projection
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: health_snapshot_competition_projection.zip
YAML
}

resource "kubectl_manifest" "pl_fn_health_snapshot_competition_projection" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-health_snapshot_competition_projection
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-health_snapshot_competition_projection
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-health_snapshot_competition_projection
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "health_snapshot_competition_projection"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 512Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_health_snapshot_competition_projection" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-health_snapshot_competition_projection
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-health_snapshot_competition_projection
  methods:
    - POST
  relativeurl: /health_snapshot_competition_projection
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_health_update_competition" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-health_update_competition
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: health_update_competition.zip
YAML
}

resource "kubectl_manifest" "pl_fn_health_update_competition" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-health_update_competition
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-health_update_competition
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-health_update_competition
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "health_update_competition"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_health_update_competition" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-health_update_competition
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-health_update_competition
  methods:
    - POST
  relativeurl: /health_update_competition
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_health_update_current_maxes" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-health_update_current_maxes
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: health_update_current_maxes.zip
YAML
}

resource "kubectl_manifest" "pl_fn_health_update_current_maxes" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-health_update_current_maxes
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-health_update_current_maxes
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-health_update_current_maxes
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "health_update_current_maxes"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_health_update_current_maxes" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-health_update_current_maxes
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-health_update_current_maxes
  methods:
    - POST
  relativeurl: /health_update_current_maxes
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_health_update_diet_note" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-health_update_diet_note
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: health_update_diet_note.zip
YAML
}

resource "kubectl_manifest" "pl_fn_health_update_diet_note" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-health_update_diet_note
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-health_update_diet_note
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-health_update_diet_note
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "health_update_diet_note"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_health_update_diet_note" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-health_update_diet_note
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-health_update_diet_note
  methods:
    - POST
  relativeurl: /health_update_diet_note
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_health_update_federation_library" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-health_update_federation_library
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: health_update_federation_library.zip
YAML
}

resource "kubectl_manifest" "pl_fn_health_update_federation_library" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-health_update_federation_library
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-health_update_federation_library
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-health_update_federation_library
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "health_update_federation_library"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_health_update_federation_library" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-health_update_federation_library
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-health_update_federation_library
  methods:
    - POST
  relativeurl: /health_update_federation_library
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_health_update_goals" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-health_update_goals
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: health_update_goals.zip
YAML
}

resource "kubectl_manifest" "pl_fn_health_update_goals" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-health_update_goals
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-health_update_goals
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-health_update_goals
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "health_update_goals"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_health_update_goals" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-health_update_goals
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-health_update_goals
  methods:
    - POST
  relativeurl: /health_update_goals
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_health_update_meta" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-health_update_meta
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: health_update_meta.zip
YAML
}

resource "kubectl_manifest" "pl_fn_health_update_meta" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-health_update_meta
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-health_update_meta
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-health_update_meta
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "health_update_meta"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_health_update_meta" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-health_update_meta
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-health_update_meta
  methods:
    - POST
  relativeurl: /health_update_meta
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_health_update_phases" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-health_update_phases
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: health_update_phases.zip
YAML
}

resource "kubectl_manifest" "pl_fn_health_update_phases" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-health_update_phases
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-health_update_phases
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-health_update_phases
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "health_update_phases"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_health_update_phases" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-health_update_phases
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-health_update_phases
  methods:
    - POST
  relativeurl: /health_update_phases
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_health_update_session" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-health_update_session
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: health_update_session.zip
YAML
}

resource "kubectl_manifest" "pl_fn_health_update_session" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-health_update_session
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-health_update_session
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-health_update_session
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "health_update_session"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_health_update_session" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-health_update_session
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-health_update_session
  methods:
    - POST
  relativeurl: /health_update_session
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_health_update_supplements" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-health_update_supplements
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: health_update_supplements.zip
YAML
}

resource "kubectl_manifest" "pl_fn_health_update_supplements" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-health_update_supplements
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-health_update_supplements
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-health_update_supplements
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "health_update_supplements"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_health_update_supplements" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-health_update_supplements
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-health_update_supplements
  methods:
    - POST
  relativeurl: /health_update_supplements
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_import_apply" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-import_apply
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: import_apply.zip
YAML
}

resource "kubectl_manifest" "pl_fn_import_apply" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-import_apply
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-import_apply
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-import_apply
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "import_apply"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 512Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_import_apply" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-import_apply
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-import_apply
  methods:
    - POST
  relativeurl: /import_apply
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_import_get_pending" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-import_get_pending
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: import_get_pending.zip
YAML
}

resource "kubectl_manifest" "pl_fn_import_get_pending" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-import_get_pending
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-import_get_pending
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-import_get_pending
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "import_get_pending"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_import_get_pending" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-import_get_pending
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-import_get_pending
  methods:
    - POST
  relativeurl: /import_get_pending
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_import_list_pending" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-import_list_pending
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: import_list_pending.zip
YAML
}

resource "kubectl_manifest" "pl_fn_import_list_pending" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-import_list_pending
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-import_list_pending
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-import_list_pending
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "import_list_pending"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_import_list_pending" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-import_list_pending
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-import_list_pending
  methods:
    - POST
  relativeurl: /import_list_pending
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_import_parse_file" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-import_parse_file
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: import_parse_file.zip
YAML
}

resource "kubectl_manifest" "pl_fn_import_parse_file" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-import_parse_file
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-import_parse_file
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 1
            SpecializationTimeout: 120
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-import_parse_file
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: ANALYSIS_MODEL
              value: "anthropic/claude-sonnet-4.6"
            - name: ESTIMATE_MODEL
              value: "anthropic/claude-sonnet-4.6"
            - name: IMPORT_FAST_MODEL
              value: "anthropic/claude-haiku-4.5"
            - name: GLOSSARY_TEXT_MODEL
              value: "google/gemini-3.1-flash-lite"
            - name: IF_TOOL_NAME
              value: "import_parse_file"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 512Mi
          limits:
            cpu: 1000m
            memory: 1024Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_import_parse_file" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-import_parse_file
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-import_parse_file
  methods:
    - POST
  relativeurl: /import_parse_file
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_import_reject" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-import_reject
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: import_reject.zip
YAML
}

resource "kubectl_manifest" "pl_fn_import_reject" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-import_reject
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-import_reject
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-import_reject
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "import_reject"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_import_reject" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-import_reject
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-import_reject
  methods:
    - POST
  relativeurl: /import_reject
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_ipf_weight_classes" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-ipf_weight_classes
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: ipf_weight_classes.zip
YAML
}

resource "kubectl_manifest" "pl_fn_ipf_weight_classes" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-ipf_weight_classes
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-ipf_weight_classes
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-ipf_weight_classes
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "ipf_weight_classes"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 128Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_ipf_weight_classes" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-ipf_weight_classes
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-ipf_weight_classes
  methods:
    - POST
  relativeurl: /ipf_weight_classes
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_kg_to_lb" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-kg_to_lb
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: kg_to_lb.zip
YAML
}

resource "kubectl_manifest" "pl_fn_kg_to_lb" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-kg_to_lb
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-kg_to_lb
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-kg_to_lb
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "kg_to_lb"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 128Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_kg_to_lb" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-kg_to_lb
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-kg_to_lb
  methods:
    - POST
  relativeurl: /kg_to_lb
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_lb_to_kg" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-lb_to_kg
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: lb_to_kg.zip
YAML
}

resource "kubectl_manifest" "pl_fn_lb_to_kg" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-lb_to_kg
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-lb_to_kg
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-lb_to_kg
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "lb_to_kg"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 128Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_lb_to_kg" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-lb_to_kg
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-lb_to_kg
  methods:
    - POST
  relativeurl: /lb_to_kg
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_lift_profile_estimate_stimulus" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-lift_profile_estimate_stimulus
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: lift_profile_estimate_stimulus.zip
YAML
}

resource "kubectl_manifest" "pl_fn_lift_profile_estimate_stimulus" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-lift_profile_estimate_stimulus
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-lift_profile_estimate_stimulus
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 1
            SpecializationTimeout: 120
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-lift_profile_estimate_stimulus
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: ANALYSIS_MODEL
              value: "anthropic/claude-sonnet-4.6"
            - name: ESTIMATE_MODEL
              value: "anthropic/claude-sonnet-4.6"
            - name: IMPORT_FAST_MODEL
              value: "anthropic/claude-haiku-4.5"
            - name: GLOSSARY_TEXT_MODEL
              value: "google/gemini-3.1-flash-lite"
            - name: IF_TOOL_NAME
              value: "lift_profile_estimate_stimulus"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 512Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_lift_profile_estimate_stimulus" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-lift_profile_estimate_stimulus
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-lift_profile_estimate_stimulus
  methods:
    - POST
  relativeurl: /lift_profile_estimate_stimulus
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_lift_profile_review" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-lift_profile_review
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: lift_profile_review.zip
YAML
}

resource "kubectl_manifest" "pl_fn_lift_profile_review" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-lift_profile_review
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-lift_profile_review
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 1
            SpecializationTimeout: 120
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-lift_profile_review
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: ANALYSIS_MODEL
              value: "anthropic/claude-sonnet-4.6"
            - name: ESTIMATE_MODEL
              value: "anthropic/claude-sonnet-4.6"
            - name: IMPORT_FAST_MODEL
              value: "anthropic/claude-haiku-4.5"
            - name: GLOSSARY_TEXT_MODEL
              value: "google/gemini-3.1-flash-lite"
            - name: IF_TOOL_NAME
              value: "lift_profile_review"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 512Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_lift_profile_review" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-lift_profile_review
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-lift_profile_review
  methods:
    - POST
  relativeurl: /lift_profile_review
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_lift_profile_rewrite" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-lift_profile_rewrite
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: lift_profile_rewrite.zip
YAML
}

resource "kubectl_manifest" "pl_fn_lift_profile_rewrite" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-lift_profile_rewrite
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-lift_profile_rewrite
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 1
            SpecializationTimeout: 120
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-lift_profile_rewrite
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: ANALYSIS_MODEL
              value: "anthropic/claude-sonnet-4.6"
            - name: ESTIMATE_MODEL
              value: "anthropic/claude-sonnet-4.6"
            - name: IMPORT_FAST_MODEL
              value: "anthropic/claude-haiku-4.5"
            - name: GLOSSARY_TEXT_MODEL
              value: "google/gemini-3.1-flash-lite"
            - name: IF_TOOL_NAME
              value: "lift_profile_rewrite"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 512Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_lift_profile_rewrite" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-lift_profile_rewrite
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-lift_profile_rewrite
  methods:
    - POST
  relativeurl: /lift_profile_rewrite
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_lift_profile_rewrite_and_estimate" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-lift_profile_rewrite_and_estimate
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: lift_profile_rewrite_and_estimate.zip
YAML
}

resource "kubectl_manifest" "pl_fn_lift_profile_rewrite_and_estimate" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-lift_profile_rewrite_and_estimate
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-lift_profile_rewrite_and_estimate
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-lift_profile_rewrite_and_estimate
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "lift_profile_rewrite_and_estimate"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 512Mi
          limits:
            cpu: 1000m
            memory: 1024Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_lift_profile_rewrite_and_estimate" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-lift_profile_rewrite_and_estimate
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-lift_profile_rewrite_and_estimate
  methods:
    - POST
  relativeurl: /lift_profile_rewrite_and_estimate
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_master_sync" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-master-sync
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: master-sync.zip
YAML
}

resource "kubectl_manifest" "pl_fn_master_sync" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-master-sync
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-master-sync
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-master-sync
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "master-sync"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 512Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_master_sync" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-master-sync
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-master-sync
  methods:
    - POST
  relativeurl: /master-sync
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_multi_block_comparison_analysis" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-multi_block_comparison_analysis
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: multi_block_comparison_analysis.zip
YAML
}

resource "kubectl_manifest" "pl_fn_multi_block_comparison_analysis" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-multi_block_comparison_analysis
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-multi_block_comparison_analysis
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-multi_block_comparison_analysis
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "multi_block_comparison_analysis"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 512Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_multi_block_comparison_analysis" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-multi_block_comparison_analysis
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-multi_block_comparison_analysis
  methods:
    - POST
  relativeurl: /multi_block_comparison_analysis
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_muscle_group_estimate" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-muscle_group_estimate
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: muscle_group_estimate.zip
YAML
}

resource "kubectl_manifest" "pl_fn_muscle_group_estimate" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-muscle_group_estimate
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-muscle_group_estimate
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 1
            SpecializationTimeout: 120
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-muscle_group_estimate
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: ANALYSIS_MODEL
              value: "anthropic/claude-sonnet-4.6"
            - name: ESTIMATE_MODEL
              value: "anthropic/claude-sonnet-4.6"
            - name: IMPORT_FAST_MODEL
              value: "anthropic/claude-haiku-4.5"
            - name: GLOSSARY_TEXT_MODEL
              value: "google/gemini-3.1-flash-lite"
            - name: IF_TOOL_NAME
              value: "muscle_group_estimate"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 512Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_muscle_group_estimate" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-muscle_group_estimate
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-muscle_group_estimate
  methods:
    - POST
  relativeurl: /muscle_group_estimate
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_pct_of_max" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-pct_of_max
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: pct_of_max.zip
YAML
}

resource "kubectl_manifest" "pl_fn_pct_of_max" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-pct_of_max
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-pct_of_max
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-pct_of_max
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "pct_of_max"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 128Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_pct_of_max" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-pct_of_max
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-pct_of_max
  methods:
    - POST
  relativeurl: /pct_of_max
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_powerlifting_filter_categories" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-powerlifting_filter_categories
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: powerlifting_filter_categories.zip
YAML
}

resource "kubectl_manifest" "pl_fn_powerlifting_filter_categories" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-powerlifting_filter_categories
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-powerlifting_filter_categories
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 2
            SpecializationTimeout: 120
            TargetCPUPercent: 80
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-powerlifting_filter_categories
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: POWERLIFTING_S3_BUCKET
              value: "${var.powerlifting_s3_bucket}"
            - name: IF_TOOL_NAME
              value: "powerlifting_filter_categories"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 512Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_powerlifting_filter_categories" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-powerlifting_filter_categories
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-powerlifting_filter_categories
  methods:
    - POST
  relativeurl: /powerlifting_filter_categories
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_powerlifting_ranking_percentile" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-powerlifting_ranking_percentile
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: powerlifting_ranking_percentile.zip
YAML
}

resource "kubectl_manifest" "pl_fn_powerlifting_ranking_percentile" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-powerlifting_ranking_percentile
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-powerlifting_ranking_percentile
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 2
            SpecializationTimeout: 120
            TargetCPUPercent: 80
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-powerlifting_ranking_percentile
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: POWERLIFTING_S3_BUCKET
              value: "${var.powerlifting_s3_bucket}"
            - name: IF_TOOL_NAME
              value: "powerlifting_ranking_percentile"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 512Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_powerlifting_ranking_percentile" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-powerlifting_ranking_percentile
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-powerlifting_ranking_percentile
  methods:
    - POST
  relativeurl: /powerlifting_ranking_percentile
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_program_archive" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-program_archive
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: program_archive.zip
YAML
}

resource "kubectl_manifest" "pl_fn_program_archive" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-program_archive
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-program_archive
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-program_archive
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "program_archive"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_program_archive" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-program_archive
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-program_archive
  methods:
    - POST
  relativeurl: /program_archive
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_program_evaluation" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-program_evaluation
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: program_evaluation.zip
YAML
}

resource "kubectl_manifest" "pl_fn_program_evaluation" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-program_evaluation
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-program_evaluation
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 1
            SpecializationTimeout: 120
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-program_evaluation
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: ANALYSIS_MODEL
              value: "anthropic/claude-sonnet-4.6"
            - name: ESTIMATE_MODEL
              value: "anthropic/claude-sonnet-4.6"
            - name: IMPORT_FAST_MODEL
              value: "anthropic/claude-haiku-4.5"
            - name: GLOSSARY_TEXT_MODEL
              value: "google/gemini-3.1-flash-lite"
            - name: IF_TOOL_NAME
              value: "program_evaluation"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 512Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_program_evaluation" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-program_evaluation
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-program_evaluation
  methods:
    - POST
  relativeurl: /program_evaluation
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_program_unarchive" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-program_unarchive
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: program_unarchive.zip
YAML
}

resource "kubectl_manifest" "pl_fn_program_unarchive" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-program_unarchive
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-program_unarchive
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-program_unarchive
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "program_unarchive"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_program_unarchive" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-program_unarchive
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-program_unarchive
  methods:
    - POST
  relativeurl: /program_unarchive
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_regenerate_analysis" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-regenerate_analysis
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: regenerate_analysis.zip
YAML
}

resource "kubectl_manifest" "pl_fn_regenerate_analysis" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-regenerate_analysis
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-regenerate_analysis
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-regenerate_analysis
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "regenerate_analysis"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 512Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_regenerate_analysis" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-regenerate_analysis
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-regenerate_analysis
  methods:
    - POST
  relativeurl: /regenerate_analysis
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_template_apply" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-template_apply
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: template_apply.zip
YAML
}

resource "kubectl_manifest" "pl_fn_template_apply" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-template_apply
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-template_apply
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-template_apply
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "template_apply"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 512Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_template_apply" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-template_apply
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-template_apply
  methods:
    - POST
  relativeurl: /template_apply
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_template_apply_confirm" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-template_apply_confirm
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: template_apply_confirm.zip
YAML
}

resource "kubectl_manifest" "pl_fn_template_apply_confirm" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-template_apply_confirm
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-template_apply_confirm
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-template_apply_confirm
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "template_apply_confirm"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 512Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_template_apply_confirm" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-template_apply_confirm
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-template_apply_confirm
  methods:
    - POST
  relativeurl: /template_apply_confirm
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_template_archive" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-template_archive
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: template_archive.zip
YAML
}

resource "kubectl_manifest" "pl_fn_template_archive" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-template_archive
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-template_archive
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-template_archive
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "template_archive"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_template_archive" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-template_archive
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-template_archive
  methods:
    - POST
  relativeurl: /template_archive
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_template_copy" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-template_copy
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: template_copy.zip
YAML
}

resource "kubectl_manifest" "pl_fn_template_copy" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-template_copy
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-template_copy
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-template_copy
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "template_copy"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_template_copy" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-template_copy
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-template_copy
  methods:
    - POST
  relativeurl: /template_copy
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_template_create_blank" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-template_create_blank
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: template_create_blank.zip
YAML
}

resource "kubectl_manifest" "pl_fn_template_create_blank" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-template_create_blank
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-template_create_blank
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-template_create_blank
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "template_create_blank"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_template_create_blank" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-template_create_blank
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-template_create_blank
  methods:
    - POST
  relativeurl: /template_create_blank
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_template_create_from_block" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-template_create_from_block
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: template_create_from_block.zip
YAML
}

resource "kubectl_manifest" "pl_fn_template_create_from_block" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-template_create_from_block
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-template_create_from_block
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-template_create_from_block
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "template_create_from_block"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_template_create_from_block" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-template_create_from_block
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-template_create_from_block
  methods:
    - POST
  relativeurl: /template_create_from_block
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_template_create_from_payload" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-template_create_from_payload
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: template_create_from_payload.zip
YAML
}

resource "kubectl_manifest" "pl_fn_template_create_from_payload" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-template_create_from_payload
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-template_create_from_payload
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-template_create_from_payload
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "template_create_from_payload"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_template_create_from_payload" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-template_create_from_payload
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-template_create_from_payload
  methods:
    - POST
  relativeurl: /template_create_from_payload
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_template_evaluate" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-template_evaluate
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: template_evaluate.zip
YAML
}

resource "kubectl_manifest" "pl_fn_template_evaluate" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-template_evaluate
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-template_evaluate
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 1
            SpecializationTimeout: 120
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-template_evaluate
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: ANALYSIS_MODEL
              value: "anthropic/claude-sonnet-4.6"
            - name: ESTIMATE_MODEL
              value: "anthropic/claude-sonnet-4.6"
            - name: IMPORT_FAST_MODEL
              value: "anthropic/claude-haiku-4.5"
            - name: GLOSSARY_TEXT_MODEL
              value: "google/gemini-3.1-flash-lite"
            - name: IF_TOOL_NAME
              value: "template_evaluate"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 512Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_template_evaluate" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-template_evaluate
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-template_evaluate
  methods:
    - POST
  relativeurl: /template_evaluate
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_template_get" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-template_get
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: template_get.zip
YAML
}

resource "kubectl_manifest" "pl_fn_template_get" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-template_get
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-template_get
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 1
            MaxScale: 2
            SpecializationTimeout: 60
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-template_get
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "template_get"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_template_get" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-template_get
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-template_get
  methods:
    - POST
  relativeurl: /template_get
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_template_list" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-template_list
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: template_list.zip
YAML
}

resource "kubectl_manifest" "pl_fn_template_list" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-template_list
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-template_list
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 1
            MaxScale: 2
            SpecializationTimeout: 60
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-template_list
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "template_list"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_template_list" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-template_list
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-template_list
  methods:
    - POST
  relativeurl: /template_list
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_template_publish" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-template_publish
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: template_publish.zip
YAML
}

resource "kubectl_manifest" "pl_fn_template_publish" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-template_publish
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-template_publish
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-template_publish
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "template_publish"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_template_publish" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-template_publish
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-template_publish
  methods:
    - POST
  relativeurl: /template_publish
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_template_unarchive" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-template_unarchive
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: template_unarchive.zip
YAML
}

resource "kubectl_manifest" "pl_fn_template_unarchive" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-template_unarchive
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-template_unarchive
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-template_unarchive
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "template_unarchive"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_template_unarchive" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-template_unarchive
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-template_unarchive
  methods:
    - POST
  relativeurl: /template_unarchive
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_template_unpublish" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-template_unpublish
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: template_unpublish.zip
YAML
}

resource "kubectl_manifest" "pl_fn_template_unpublish" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-template_unpublish
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-template_unpublish
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-template_unpublish
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "template_unpublish"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_template_unpublish" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-template_unpublish
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-template_unpublish
  methods:
    - POST
  relativeurl: /template_unpublish
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_template_update" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-template_update
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: template_update.zip
YAML
}

resource "kubectl_manifest" "pl_fn_template_update" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-template_update
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-template_update
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-template_update
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "template_update"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 256Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_template_update" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-template_update
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-template_update
  methods:
    - POST
  relativeurl: /template_update
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_weekly_analysis" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-weekly_analysis
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: weekly_analysis.zip
YAML
}

resource "kubectl_manifest" "pl_fn_weekly_analysis" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-weekly_analysis
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-weekly_analysis
      namespace: if-portals
  functionTimeout: 900
  concurrency: 500
        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: 0
            MaxScale: 3
            SpecializationTimeout: 90
            TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-weekly_analysis
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
            - name: IF_AWS_REGION
              value: "ca-central-1"
            - name: IF_HEALTH_TABLE_NAME
              value: "if-health"
            - name: IF_TEMPLATES_TABLE_NAME
              value: "if-health-templates"
            - name: IF_SESSIONS_TABLE_NAME
              value: "if-sessions"
            - name: IF_ANALYSIS_CACHE_TABLE_NAME
              value: "if-powerlifting-analysis-cache"
            - name: HEALTH_PROGRAM_PK
              value: "operator"
            - name: LLM_BASE_URL
              value: "https://openrouter.ai/api/v1"
            - name: IF_TOOL_NAME
              value: "weekly_analysis"
          envFrom:
            - secretRef:
                name: pl-fission-secrets
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 512Mi
    volumes: []
YAML
}

resource "kubectl_manifest" "pl_ht_weekly_analysis" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-weekly_analysis
  namespace: if-portals
spec:
  functionref:
    type: name
    name: pl-fn-weekly_analysis
  methods:
    - POST
  relativeurl: /weekly_analysis
  prefn:
    - name: pl-authorizer
      namespace: if-portals
YAML
}

resource "kubectl_manifest" "pl_pkg_pl_authorizer" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-pl-authorizer
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  source:
    type: literal
    literal: pl_authorizer.zip
YAML
}

resource "kubectl_manifest" "pl_fn_pl_authorizer" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-authorizer
  namespace: if-portals
spec:
  environment:
    name: pl-fission-tools
    namespace: fission
  package:
    packageref:
      name: pl-pkg-pl-authorizer
      namespace: if-portals
  functionTimeout: 5
  InvokeStrategy:
    StrategyType: execution
    ExecutionStrategy:
      ExecutorType: newdeploy
      MinScale: 0
      MaxScale: 1
      SpecializationTimeout: 30
      TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-authorizer
        image: ghcr.io/fission/python-env
        imagePullPolicy: IfNotPresent
        env:
          - name: IF_TOOL_NAME
            value: "pl_authorizer"
          - name: INTERNAL_API_TOKEN
            valueFrom:
              secretKeyRef:
                name: pl-fission-secrets
                key: INTERNAL_API_TOKEN
        resources:
          requests:
            cpu: 50m
            memory: 64Mi
          limits:
            cpu: 200m
            memory: 128Mi
    volumes: []
YAML
}

