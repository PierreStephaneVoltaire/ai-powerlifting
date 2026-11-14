package contract

import (
	"bytes"
	_ "embed"
	"encoding/json"
	"fmt"

	"github.com/santhosh-tekuri/jsonschema/v6"
)

const Domain = "analytics-ai"

const (
	ExecutionAI            = "ai"
	ExecutionDeterministic = "deterministic"
)

//go:embed operations.json
var operationsJSON []byte

//go:embed permissions.json
var permissionsJSON []byte

type Operation struct {
	Name         string
	Description  string
	Execution    string
	Public       bool
	InternalOnly bool
	InputSchema  map[string]any
	ResultSchema map[string]any
	input        *jsonschema.Schema
	result       *jsonschema.Schema
}

type Registry struct {
	order      []string
	operations map[string]*Operation
}

type record struct {
	Name         string         `json:"name"`
	Domain       string         `json:"domain"`
	Description  string         `json:"description"`
	InputSchema  map[string]any `json:"input_schema"`
	ResultSchema map[string]any `json:"result_schema"`
	Ownership    string         `json:"ownership"`
	Execution    string         `json:"execution"`
}

func Load() (*Registry, error) {
	return Parse(operationsJSON, permissionsJSON)
}

func Parse(operations, permissionMap []byte) (*Registry, error) {
	var records []record
	if err := json.Unmarshal(operations, &records); err != nil {
		return nil, fmt.Errorf("operations: %w", err)
	}
	var permissions map[string]struct {
		InternalOnly bool `json:"internal_only"`
	}
	if err := json.Unmarshal(permissionMap, &permissions); err != nil {
		return nil, fmt.Errorf("permissions: %w", err)
	}
	registry := &Registry{operations: map[string]*Operation{}}
	for _, rec := range records {
		operation, err := build(rec, permissions[rec.Name].InternalOnly)
		if err != nil {
			return nil, err
		}
		if _, duplicate := registry.operations[rec.Name]; duplicate {
			return nil, fmt.Errorf("duplicate operation %s", rec.Name)
		}
		registry.order = append(registry.order, rec.Name)
		registry.operations[rec.Name] = operation
	}
	return registry, nil
}

func build(rec record, internalOnly bool) (*Operation, error) {
	if rec.Domain != Domain {
		return nil, fmt.Errorf("operation %s belongs to %s", rec.Name, rec.Domain)
	}
	if rec.Execution != ExecutionAI && rec.Execution != ExecutionDeterministic {
		return nil, fmt.Errorf("operation %s has unknown execution %q", rec.Name, rec.Execution)
	}
	operation := &Operation{
		Name:         rec.Name,
		Description:  rec.Description,
		Execution:    rec.Execution,
		Public:       rec.Ownership == "public",
		InternalOnly: internalOnly,
		InputSchema:  rec.InputSchema,
		ResultSchema: rec.ResultSchema,
	}
	if !operation.Public {
		defaultPK(operation.InputSchema)
	}
	var err error
	if operation.input, err = compile(rec.Name+"/input", operation.InputSchema); err != nil {
		return nil, err
	}
	if operation.result, err = compile(rec.Name+"/result", rec.ResultSchema); err != nil {
		return nil, err
	}
	return operation, nil
}

func defaultPK(schema map[string]any) {
	properties, ok := schema["properties"].(map[string]any)
	if !ok {
		properties = map[string]any{}
		schema["properties"] = properties
	}
	if _, present := properties["pk"]; !present {
		properties["pk"] = map[string]any{"type": "string", "minLength": 1}
	}
}

func compile(id string, schema map[string]any) (*jsonschema.Schema, error) {
	raw, err := json.Marshal(schema)
	if err != nil {
		return nil, err
	}
	document, err := jsonschema.UnmarshalJSON(bytes.NewReader(raw))
	if err != nil {
		return nil, err
	}
	compiler := jsonschema.NewCompiler()
	compiler.AssertFormat()
	url := "mem:///" + id + ".json"
	if err := compiler.AddResource(url, document); err != nil {
		return nil, err
	}
	return compiler.Compile(url)
}

func (r *Registry) Get(name string) (*Operation, bool) {
	operation, ok := r.operations[name]
	return operation, ok
}

func (r *Registry) All() []*Operation {
	out := make([]*Operation, 0, len(r.order))
	for _, name := range r.order {
		out = append(out, r.operations[name])
	}
	return out
}

func (o *Operation) HasInput(name string) bool {
	properties, _ := o.InputSchema["properties"].(map[string]any)
	_, ok := properties[name]
	return ok
}

func (o *Operation) ValidateInput(arguments map[string]any) error {
	return validate(o.input, arguments)
}

func (o *Operation) ValidateResult(result any) error {
	return validate(o.result, result)
}

func validate(schema *jsonschema.Schema, value any) error {
	raw, err := json.Marshal(value)
	if err != nil {
		return err
	}
	instance, err := jsonschema.UnmarshalJSON(bytes.NewReader(raw))
	if err != nil {
		return err
	}
	return schema.Validate(instance)
}

func ValidateAgainst(schema map[string]any, value any) error {
	compiled, err := compile("inline", schema)
	if err != nil {
		return err
	}
	return validate(compiled, value)
}
