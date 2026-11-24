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
var effort map[string]float64
var ipf map[string]map[string]map[string]float64

func init() {
	var constants struct {
		Dots   map[string]map[string]float64            `json:"dots_coefficients"`
		Effort map[string]float64                       `json:"rpe_percent"`
		IPF    map[string]map[string]map[string]float64 `json:"ipf_gl_coefficients"`
	}
	if err := json.Unmarshal(constantsJSON, &constants); err != nil {
		panic(err)
	}
	dots = map[string]coefficients{}
	effort, ipf = constants.Effort, constants.IPF
	for sex, values := range constants.Dots {
		dots[sex] = coefficients{values["a"], values["b"], values["c"], values["d"], values["e"]}
	}
}

func EstimatedMax(weight, reps float64, rpe *float64) (float64, bool) {
	if math.IsNaN(weight) || math.IsInf(weight, 0) || weight <= 0 || reps < 1 || reps > 10 || reps != math.Trunc(reps) {
		return 0, false
	}
	level := 10
	if rpe != nil {
		if math.IsNaN(*rpe) || *rpe < 6 || *rpe > 10 {
			return 0, false
		}
		level = int(*rpe)
	}
	percent := effort[strconv.Itoa(int(reps))+"-"+strconv.Itoa(level)]
	if percent == 0 {
		return 0, false
	}
	return Round(weight/percent, 1), true
}

func IPFScore(total, bodyweight float64, sex, mode string) (float64, bool) {
	set := ipf[mode][sex]
	if set == nil || total <= 0 || bodyweight <= 0 {
		return 0, false
	}
	denominator := set["a"] - set["b"]*math.Exp(-set["c"]*bodyweight)
	if math.Abs(denominator) < 1e-12 {
		return 0, false
	}
	return Round(100*total/denominator, 2), true
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
