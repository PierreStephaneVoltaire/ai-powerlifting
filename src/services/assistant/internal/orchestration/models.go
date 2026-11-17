package orchestration

type Tier int

const (
	TierFast Tier = iota
	TierStandard
	TierStrong
)

func (t Tier) String() string {
	switch t {
	case TierFast:
		return "fast"
	case TierStrong:
		return "strong"
	}
	return "standard"
}

type Models struct {
	Fast     string
	Standard string
	Strong   string
}

func (m Models) Model(tier Tier) string {
	switch tier {
	case TierFast:
		return m.Fast
	case TierStrong:
		return m.Strong
	}
	return m.Standard
}

func (m Models) TierOf(model string) Tier {
	switch {
	case model == m.Strong && model != m.Standard:
		return TierStrong
	case model == m.Fast && model != m.Standard:
		return TierFast
	}
	return TierStandard
}

func (m Models) Resolve(complexity, defaultModel string) Tier {
	switch complexity {
	case "low":
		return TierFast
	case "medium":
		return TierStandard
	case "high":
		return TierStrong
	}
	return m.TierOf(defaultModel)
}

func Escalate(previous, requested Tier) (Tier, bool) {
	if previous >= TierStrong {
		return previous, false
	}
	next := previous + 1
	if requested > next {
		next = requested
	}
	return next, true
}
