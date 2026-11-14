package env

import (
	"crypto/rand"
	"fmt"
	"strings"
	"time"
)

type Env struct {
	Now  func() time.Time
	UUID func() string
}

func Default() Env {
	return Env{Now: func() time.Time { return time.Now().UTC() }, UUID: randomUUID}
}

func randomUUID() string {
	var raw [16]byte
	_, _ = rand.Read(raw[:])
	raw[6] = raw[6]&0x0f | 0x40
	raw[8] = raw[8]&0x3f | 0x80
	return fmt.Sprintf("%x-%x-%x-%x-%x", raw[0:4], raw[4:6], raw[6:8], raw[8:10], raw[10:16])
}

func (e Env) Hex() string {
	return strings.ReplaceAll(e.UUID(), "-", "")
}

func (e Env) Stamp() string {
	return Iso(e.Now())
}

func Iso(moment time.Time) string {
	moment = moment.UTC()
	if moment.Nanosecond()/1000 == 0 {
		return moment.Format("2006-01-02T15:04:05") + "+00:00"
	}
	return moment.Format("2006-01-02T15:04:05.000000") + "+00:00"
}
