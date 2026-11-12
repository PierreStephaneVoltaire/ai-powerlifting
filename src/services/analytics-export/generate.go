package main

//go:generate cp ../operations/analytics-export.json internal/contract/operations.json
//go:generate cp ../permissions.json internal/contract/permissions.json
//go:generate buf generate --template buf.gen.export.yaml
//go:generate buf generate ../analytics/proto --template buf.gen.analytics.yaml
