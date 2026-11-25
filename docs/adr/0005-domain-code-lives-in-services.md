# ADR-0005: Domain code lives in Services

## Decision

Fission is retired. Domain handlers, shared stores, calculations, and AI
prompts live under `services/` and are dispatched through typed operation
manifests. Services use their implementation language's normal modules.

`lambda/` is reserved for the real AWS Lambdas: `master-sync` and
`video-thumbnail`.

## Consequences

Services own their dependencies and do not rely on layer or pod import-path
hacks. Terraform source paths for the two AWS Lambdas remain unchanged.
