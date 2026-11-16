# Bugs

- Program service: `go test ./internal/serve -run TestMCPToolsListAndCall`
  fails with `Athlete scope required` when calling `health_setup_status`.
  Reproduced against the unchanged HEAD sources on 2026-11-16 while testing
  the supplement assistant fixes; unrelated to supplement writes.
