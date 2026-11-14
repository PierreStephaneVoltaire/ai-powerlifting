package service

import (
	"os"
	"path/filepath"
	"testing"
)

func goldenPath(t *testing.T, name string) string {
	t.Helper()
	dir := os.Getenv("PL_GOLDENS_DIR")
	if dir == "" {
		t.Skip("PL_GOLDENS_DIR is not set")
	}
	return filepath.Join(dir, "competition", name)
}
