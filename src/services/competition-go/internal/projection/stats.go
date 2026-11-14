package projection

import (
	"math"
	"sort"
	"strconv"
)

func round(value float64, digits int) float64 {
	if math.IsNaN(value) || math.IsInf(value, 0) {
		return value
	}
	parsed, err := strconv.ParseFloat(strconv.FormatFloat(value, 'f', digits, 64), 64)
	if err != nil {
		return value
	}
	return parsed
}

func clamp(value, low, high float64) float64 {
	return math.Max(low, math.Min(high, value))
}

func median(values []float64) float64 {
	if len(values) == 0 {
		return math.NaN()
	}
	sorted := append([]float64(nil), values...)
	sort.Float64s(sorted)
	middle := len(sorted) / 2
	if len(sorted)%2 == 1 {
		return sorted[middle]
	}
	return (sorted[middle-1] + sorted[middle]) / 2
}

func mad(values []float64) float64 {
	if len(values) == 0 {
		return 0
	}
	center := median(values)
	deviations := make([]float64, len(values))
	for index, value := range values {
		deviations[index] = math.Abs(value - center)
	}
	return median(deviations)
}

type fit struct {
	slope     float64
	intercept float64
}

func theilSen(ys, xs []float64) fit {
	var slopes []float64
	for i := range xs {
		for j := i + 1; j < len(xs); j++ {
			dx := xs[j] - xs[i]
			if dx > 0 {
				slopes = append(slopes, (ys[j]-ys[i])/dx)
			} else if dx < 0 {
				slopes = append(slopes, (ys[i]-ys[j])/-dx)
			}
		}
	}
	slope := median(slopes)
	return fit{slope: slope, intercept: median(ys) - slope*median(xs)}
}

func fitQuality(xs, ys []float64, line fit) float64 {
	if len(xs) < 2 {
		return 0
	}
	residuals := make([]float64, len(xs))
	for index := range xs {
		residuals[index] = ys[index] - (line.intercept + line.slope*xs[index])
	}
	seriesMAD := mad(ys)
	residualMAD := mad(residuals)
	var quality float64
	if seriesMAD <= 1e-12 {
		if residualMAD <= 1e-12 {
			quality = 1
		}
	} else {
		quality = clamp(1-residualMAD/seriesMAD, 0, 1)
	}
	return round(quality, 3)
}
