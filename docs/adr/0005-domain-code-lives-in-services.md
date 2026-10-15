# ADR-0005: Domain code lives in Services

## Decision

Fission is retired. Domain handlers, shared stores, calculations, and AI
prompts live under `services/` as normal Python packages and are dispatched by
the typed operation manifests.

`lambda/` is reserved for the real AWS Lambdas: `master-sync` and
`video-thumbnail`.

## Consequences

Services use package-qualified imports with no layer or pod `sys.path` hacks.
The service image owns its complete Python dependency set. Terraform source
paths for the two AWS Lambdas remain unchanged.
