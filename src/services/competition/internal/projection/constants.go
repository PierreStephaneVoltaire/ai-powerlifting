package projection

import (
	_ "embed"
	"encoding/json"
	"strconv"
	"strings"
	"sync"
)

//go:embed constants.json
var constantsJSON []byte

type dotsCoefficients struct {
	A float64 `json:"a"`
	B float64 `json:"b"`
	C float64 `json:"c"`
	D float64 `json:"d"`
	E float64 `json:"e"`
}

type constants struct {
	RPEPercent       map[string]float64          `json:"rpe_percent"`
	DotsCoefficients map[string]dotsCoefficients `json:"dots_coefficients"`
}

var loadConstants = sync.OnceValue(func() constants {
	var loaded constants
	if err := json.Unmarshal(constantsJSON, &loaded); err != nil {
		panic("calculation constants: " + err.Error())
	}
	return loaded
})

func rpePercent(reps, rpe int) (float64, bool) {
	value, ok := loadConstants().RPEPercent[strconv.Itoa(reps)+"-"+strconv.Itoa(rpe)]
	return value, ok
}

func dotsFor(sex string) (dotsCoefficients, bool) {
	value, ok := loadConstants().DotsCoefficients[strings.ToLower(sex)]
	return value, ok
}
