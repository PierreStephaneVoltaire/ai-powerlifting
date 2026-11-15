package clock

import (
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"strings"
	"time"
)

type Env struct {
	Now func() time.Time
	ID  func() string
}

func System() Env { return Env{Now: time.Now, ID: RandomID} }

func RandomID() string {
	var raw [16]byte
	_, _ = rand.Read(raw[:])
	raw[6] = (raw[6] & 0x0f) | 0x40
	raw[8] = (raw[8] & 0x3f) | 0x80
	return hex.EncodeToString(raw[:])
}

func (e Env) Stamp() string { return ISO(e.Now()) }

func (e Env) UUID() string {
	id := e.ID()
	return id[0:8] + "-" + id[8:12] + "-" + id[12:16] + "-" + id[16:20] + "-" + id[20:32]
}

func ISO(t time.Time) string {
	t = t.UTC()
	text := t.Format("2006-01-02T15:04:05")
	if micro := t.Nanosecond() / 1000; micro != 0 {
		text += fmt.Sprintf(".%06d", micro)
	}
	return text + "+00:00"
}

var isoLayouts = []string{
	"2006-01-02T15:04:05.999999999Z07:00",
	"2006-01-02 15:04:05.999999999Z07:00",
	"2006-01-02T15:04:05.999999999",
	"2006-01-02 15:04:05.999999999",
	"2006-01-02T15:04",
	"2006-01-02",
}

func ParseISO(text string) (t time.Time, aware bool, ok bool) {
	text = strings.TrimSpace(text)
	text = strings.Replace(text, "Z", "+00:00", 1)
	for _, layout := range isoLayouts {
		if parsed, err := time.Parse(layout, text); err == nil {
			return parsed, strings.Contains(layout, "Z07:00"), true
		}
	}
	return time.Time{}, false, false
}

func Date(text string) (time.Time, bool) {
	if len(text) < 10 {
		return time.Time{}, false
	}
	parsed, err := time.Parse("2006-01-02", text[:10])
	return parsed, err == nil
}
