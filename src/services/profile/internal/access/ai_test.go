package access

import (
	"testing"
	"time"

	"powerlifting/profile/internal/value"
)

func TestAIEntitlementBelongsToPerson(t *testing.T) {
	owner := value.Item{"pk": "athlete", "mapped_pk": "athlete"}
	for _, tc := range []struct {
		name  string
		actor value.Item
		want  bool
	}{
		{"ordinary", value.Item{"pk": "person", "mapped_pk": "person"}, false},
		{"pro", value.Item{"pk": "person", "mapped_pk": "person", "ai_access": true, "ai_access_expires": 4102444800}, true},
		{"expired", value.Item{"pk": "person", "mapped_pk": "person", "ai_access": true, "ai_access_expires": 1}, false},
		{"operator", value.Item{"pk": "operator", "mapped_pk": "operator"}, true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			if got := Evaluate("person", "athlete", owner, tc.actor, nil, nil, time.Now()).Has("ai:use"); got != tc.want {
				t.Fatalf("AI access = %v, want %v", got, tc.want)
			}
		})
	}
}
