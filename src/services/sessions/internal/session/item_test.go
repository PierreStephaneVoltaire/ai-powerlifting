package session

import (
	"testing"
	"time"
)

func TestIsoTimeMatchesPythonIsoformat(t *testing.T) {
	whole := time.Date(2026, 11, 14, 12, 0, 0, 0, time.UTC)
	if got := isoTime(whole); got != "2026-11-14T12:00:00+00:00" {
		t.Fatal(got)
	}
	fractional := time.Date(2026, 11, 14, 12, 0, 0, 123000, time.FixedZone("x", 3600))
	if got := isoTime(fractional); got != "2026-11-14T11:00:00.000123+00:00" {
		t.Fatal(got)
	}
}

func TestRandomIDIsUUIDv4Shaped(t *testing.T) {
	id := RandomID()
	if len(id) != 36 || id[14] != '4' || id == RandomID() {
		t.Fatal(id)
	}
}
