package store

import (
	"fmt"
	"time"
)

const TimestampLayout = "20060102T150405Z"

func LatestKey(athlete, extension string) string {
	return fmt.Sprintf("lifetime/%s/latest.%s", athlete, extension)
}

func StampedKey(athlete string, at time.Time, extension string) string {
	return fmt.Sprintf("lifetime/%s/%s.%s", athlete, at.UTC().Format(TimestampLayout), extension)
}
