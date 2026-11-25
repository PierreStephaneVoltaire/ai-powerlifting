package contract

import "testing"

func TestLoadTemplateOperations(t *testing.T) {
	registry, err := Load()
	if err != nil {
		t.Fatal(err)
	}
	if len(registry.All()) != 18 {
		t.Fatalf("got %d template operations", len(registry.All()))
	}
}
