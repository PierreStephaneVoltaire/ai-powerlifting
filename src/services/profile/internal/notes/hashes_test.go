package notes

import (
	"testing"

	"powerlifting/profile/internal/value"
)

func TestDerivedNoteIDsAndPayloadHashesMatchPython(t *testing.T) {
	if got := uuid5("authored-note:person_alice:k2"); got != "ad85d812-ce52-5a4c-90f0-ff349ae66879" {
		t.Errorf("uuid5 %s", got)
	}
	hash := payloadHash(map[string]any{"note_id": nil, "text": "café \U0001F3CB", "expected_revision": value.Int(0)})
	if hash != "e145df021e113f3d6c2b972b4902587ebd9017bfb5f63a25d72174621c59b766" {
		t.Errorf("payload hash %s", hash)
	}
}
