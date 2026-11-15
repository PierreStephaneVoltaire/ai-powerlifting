package calc

import (
	_ "embed"
	"encoding/json"
	"errors"
	"math"
	"strconv"
	"strings"
)

//go:embed calculation_constants.json
var constantsJSON []byte

type coefficients struct {
	A, B, C, D, E float64
}

var dots map[string]coefficients

func init() {
	var constants struct {
		Dots map[string]map[string]float64 `json:"dots_coefficients"`
	}
	if err := json.Unmarshal(constantsJSON, &constants); err != nil {
		panic(err)
	}
	dots = map[string]coefficients{}
	for sex, values := range constants.Dots {
		dots[sex] = coefficients{values["a"], values["b"], values["c"], values["d"], values["e"]}
	}
}

func Round(value float64, digits int) float64 {
	parsed, err := strconv.ParseFloat(strconv.FormatFloat(value, 'f', digits, 64), 64)
	if err != nil {
		return value
	}
	return parsed
}

func Dots(total, bodyweight float64, sex string) (float64, error) {
	set, ok := dots[strings.ToLower(sex)]
	if !ok {
		return 0, errors.New("Expected male or female")
	}
	if math.IsNaN(total) || math.IsInf(total, 0) || math.IsNaN(bodyweight) || math.IsInf(bodyweight, 0) || total < 0 || bodyweight <= 0 {
		return 0, errors.New("Expected nonnegative total and positive bodyweight")
	}
	denominator := set.A + set.B*bodyweight + set.C*math.Pow(bodyweight, 2) + set.D*math.Pow(bodyweight, 3) + set.E*math.Pow(bodyweight, 4)
	if math.Abs(denominator) < 1e-12 {
		return 0, nil
	}
	return Round(500*total/denominator, 2), nil
}
