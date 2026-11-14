package views

import "testing"

func TestSearchFingerprintMatchesPython(t *testing.T) {
	if got, want := fingerprint("q", []string{"IPF", "CPU"}, []string{"Strong"}, "and", ""), "e9d8806994148834e70c91b3e4072199fde48628925b104bff446e7bba12d53d"; got != want {
		t.Errorf("got %s want %s", got, want)
	}
	if got, want := fingerprint("straße", nil, nil, "or", "coach"), "d460809949ccfe814e71635b23adf7364de005c1eb3a8969223ef839583db991"; got != want {
		t.Errorf("got %s want %s", got, want)
	}
}
