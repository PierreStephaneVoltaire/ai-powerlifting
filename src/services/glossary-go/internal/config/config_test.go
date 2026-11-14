package config

import "testing"

func setAll(t *testing.T) {
	for name, value := range map[string]string{
		"PL_PROFILE_URL": "http://profile/", "VALKEY_URL": "redis://v", "IF_API_URL": "http://coach/", "GLOSSARY_TABLE_NAME": "g",
		"IF_HEALTH_TABLE_NAME": "h", "IF_SESSIONS_TABLE_NAME": "s", "GLOSSARY_GENERIC_INTERVAL": "5m",
	} {
		t.Setenv(name, value)
	}
}

func TestFromEnv(t *testing.T) {
	setAll(t)
	cfg, err := FromEnv()
	if err != nil || cfg.GenericInterval.Minutes() != 5 || cfg.ProfileURL != "http://profile" || cfg.CoachURL != "http://coach" || cfg.Port != "8000" {
		t.Fatalf("cfg %+v err %v", cfg, err)
	}
}

func TestFromEnvRejectsMissingAndBadValues(t *testing.T) {
	setAll(t)
	t.Setenv("GLOSSARY_TABLE_NAME", "")
	if _, err := FromEnv(); err == nil {
		t.Fatal("missing table accepted")
	}
	setAll(t)
	t.Setenv("GLOSSARY_GENERIC_INTERVAL", "soon")
	if _, err := FromEnv(); err == nil {
		t.Fatal("bad interval accepted")
	}
}
