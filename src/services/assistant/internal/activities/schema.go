package activities

import (
	"bytes"
	"encoding/json"
	"strings"

	"github.com/santhosh-tekuri/jsonschema/v6"

	"powerlifting/assistant/internal/agent"
)

const schemaResource = "operation.json"

func validateArguments(schema json.RawMessage, arguments map[string]any) string {
	if len(bytes.TrimSpace(schema)) == 0 || string(bytes.TrimSpace(schema)) == "null" {
		return ""
	}
	document, err := jsonschema.UnmarshalJSON(bytes.NewReader(schema))
	if err != nil {
		return ""
	}
	compiler := jsonschema.NewCompiler()
	if err := compiler.AddResource(schemaResource, document); err != nil {
		return ""
	}
	compiled, err := compiler.Compile(schemaResource)
	if err != nil {
		return ""
	}
	if arguments == nil {
		arguments = map[string]any{}
	}
	instance, err := jsonschema.UnmarshalJSON(strings.NewReader(string(mustJSON(arguments))))
	if err != nil {
		return err.Error()
	}
	if err := compiled.Validate(instance); err != nil {
		return agent.Truncate(strings.Join(strings.Fields(err.Error()), " "), 1200)
	}
	return ""
}
