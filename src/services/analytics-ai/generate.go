package main

//go:generate cp ../operations/analytics-ai.json internal/contract/operations.json
//go:generate cp ../runtime/permissions.json internal/contract/permissions.json
//go:generate buf generate --template buf.gen.reports.yaml
//go:generate buf generate ../analytics/proto --template buf.gen.analytics.yaml
//go:generate buf generate ../analytics-export/proto --template buf.gen.export.yaml
