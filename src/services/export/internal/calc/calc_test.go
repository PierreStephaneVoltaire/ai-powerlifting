package calc

import (
	"bytes"
	"os"
	"testing"
)

func TestSharedCalculationDataAndScores(t *testing.T) {
	data, err := os.ReadFile("../../../runtime/calculation_constants.json")
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(data, constantsJSON) {
		t.Fatal("calculation data differs from shared definitions")
	}
	rpe := 8.5
	if max, ok := EstimatedMax(80, 5, &rpe); !ok || max != 98.2 {
		t.Fatalf("estimated max %v, %v", max, ok)
	}
	if score, ok := IPFScore(100, 80, "male", "classic_bench"); !ok || score <= 0 {
		t.Fatalf("score %v, %v", score, ok)
	}
}
