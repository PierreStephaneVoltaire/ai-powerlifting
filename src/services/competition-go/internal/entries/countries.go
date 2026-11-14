package entries

import (
	"strings"

	"powerlifting/competition/internal/pyval"
)

var countryCodes = map[string]string{
	"usa": "us", "united states": "us", "united states of america": "us",
	"canada": "ca", "uk": "gb", "united kingdom": "gb", "great britain": "gb",
	"england": "gb", "scotland": "gb", "wales": "gb", "northern ireland": "gb",
	"australia": "au", "new zealand": "nz", "ireland": "ie", "mexico": "mx",
	"germany": "de", "france": "fr", "spain": "es", "italy": "it",
	"netherlands": "nl", "belgium": "be", "sweden": "se", "norway": "no",
	"finland": "fi", "denmark": "dk", "poland": "pl", "russia": "ru",
	"ukraine": "ua", "japan": "jp", "south africa": "za", "brazil": "br",
	"argentina": "ar",
}

func countryCode(value any) string {
	if !pyval.Truthy(value) {
		return ""
	}
	text := strings.ToLower(strings.TrimSpace(pyval.Str(value)))
	if text == "" {
		return ""
	}
	if code, ok := countryCodes[text]; ok {
		return code
	}
	return text
}
