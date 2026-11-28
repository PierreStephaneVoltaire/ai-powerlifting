package domainjobs

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/santhosh-tekuri/jsonschema/v6"
)

type Model struct {
	Model  string `json:"model"`
	Effort string `json:"effort"`
}

type Operation struct {
	Name        string          `json:"name"`
	Domain      string          `json:"domain"`
	Execution   string          `json:"execution"`
	InputSchema json.RawMessage `json:"input_schema"`
	schema      *jsonschema.Schema
}

func (o Operation) Inference() bool { return o.Execution == "ai" }

func (o Operation) Validate(arguments any) error {
	if o.schema == nil {
		return nil
	}
	return o.schema.Validate(arguments)
}

func compileSchema(raw json.RawMessage) (*jsonschema.Schema, error) {
	schema, err := jsonschema.UnmarshalJSON(bytes.NewReader(raw))
	if err != nil {
		return nil, err
	}
	compiler := jsonschema.NewCompiler()
	if err := compiler.AddResource("operation.json", schema); err != nil {
		return nil, err
	}
	return compiler.Compile("operation.json")
}

func LoadCatalog(directory, permissionsFile, modelConfig string) (map[string]Operation, map[string]Model, error) {
	permissionsRaw, err := os.ReadFile(permissionsFile)
	if err != nil {
		return nil, nil, err
	}
	var permissions map[string]struct {
		Internal bool `json:"internal_only"`
	}
	if err := json.Unmarshal(permissionsRaw, &permissions); err != nil {
		return nil, nil, err
	}
	var models map[string]Model
	if err := json.Unmarshal([]byte(modelConfig), &models); err != nil {
		return nil, nil, fmt.Errorf("invalid domain operation model configuration: %w", err)
	}
	files, err := filepath.Glob(filepath.Join(directory, "*.json"))
	if err != nil || len(files) == 0 {
		return nil, nil, fmt.Errorf("no domain operation manifests in %s", directory)
	}
	catalog := map[string]Operation{}
	for _, file := range files {
		raw, err := os.ReadFile(file)
		if err != nil {
			return nil, nil, err
		}
		var operations []Operation
		if err := json.Unmarshal(raw, &operations); err != nil {
			return nil, nil, err
		}
		for _, operation := range operations {
			if permissions[operation.Name].Internal {
				continue
			}
			if operation.Inference() && (models[operation.Name].Model == "" || models[operation.Name].Effort == "") {
				return nil, nil, fmt.Errorf("missing model or effort for %s", operation.Name)
			}
			if len(operation.InputSchema) != 0 && string(operation.InputSchema) != "null" {
				operation.schema, err = compileSchema(operation.InputSchema)
				if err != nil {
					return nil, nil, fmt.Errorf("invalid schema for %s: %w", operation.Name, err)
				}
			}
			catalog[operation.Name] = operation
		}
	}
	return catalog, models, nil
}

func ScopeConflict(value any, athlete string) bool {
	switch value := value.(type) {
	case map[string]any:
		for key, item := range value {
			if key == "_report_source" {
				continue
			}
			switch key {
			case "athlete", "pk", "user_pk", "mapped_pk", "person_pk", "_user_pk":
				if subject, ok := item.(string); !ok || subject != athlete {
					return true
				}
			}
			if ScopeConflict(item, athlete) {
				return true
			}
		}
	case []any:
		for _, item := range value {
			if ScopeConflict(item, athlete) {
				return true
			}
		}
	}
	return false
}

func TrustedArguments(args map[string]any, caller, domain string) bool {
	for key := range args {
		if strings.HasPrefix(key, "_") && (key != "_report_source" || caller != "pl-"+domain) {
			return false
		}
	}
	return true
}
