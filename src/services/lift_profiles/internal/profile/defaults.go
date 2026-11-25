package profile

import _ "embed"

//go:embed options.json
var optionData []byte

func Defaults() (Definitions, error) { return Parse(optionData) }
