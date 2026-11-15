package estimate

import "errors"

type E1RM struct {
	Kg, Ratio                      float64
	PrimaryLift, Basis, Confidence string
}

func parseE1RM(raw any) (E1RM, error) {
	args, _ := raw.(map[string]any)
	estimate := E1RM{Kg: number(args["e1rm_kg"]), Ratio: number(args["ratio"])}
	estimate.PrimaryLift, _ = args["primary_lift_used"].(string)
	estimate.Basis, _ = args["basis"].(string)
	estimate.Confidence, _ = args["confidence"].(string)
	if estimate.Kg <= 0 {
		return E1RM{}, errors.New("e1rm has no usable value")
	}
	return estimate, nil
}
