package activities

import (
	"context"
	"strings"
	"time"

	"powerlifting/assistant/internal/store"
)

const (
	progressInterval = 500 * time.Millisecond
	progressChars    = 400
)

type progressStream struct {
	ctx     context.Context
	store   *store.Store
	turnID  string
	stage   string
	text    strings.Builder
	pending int
	last    time.Time
}

func newProgressStream(ctx context.Context, s *store.Store, turnID, stage string) *progressStream {
	stream := &progressStream{ctx: ctx, store: s, turnID: turnID, stage: stage}
	stream.text.WriteString("\n\n" + stage + "\n")
	stream.last = time.Now()
	return stream
}

func (p *progressStream) Add(text string) {
	p.text.WriteString(text)
	p.pending += len(text)
	if p.pending >= progressChars || time.Since(p.last) >= progressInterval {
		p.Flush()
	}
}

func (p *progressStream) Flush() {
	if p.pending == 0 {
		return
	}
	if err := p.store.AppendProgress(p.ctx, p.turnID, p.stage, p.text.String()); err != nil {
		return
	}
	p.text.Reset()
	p.pending = 0
	p.last = time.Now()
}
