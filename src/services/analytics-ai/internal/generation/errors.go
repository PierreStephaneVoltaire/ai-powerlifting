package generation

import "errors"

var (
	ErrRegenerate    = errors.New("This saved result needs to be regenerated with current access")
	ErrAccessChanged = errors.New("Access to this saved result has changed")
	ErrOutsideGrant  = errors.New("This saved result includes Competition Entries outside the current grant")
	ErrIncomplete    = errors.New("Report result is incomplete; explicitly retry")
)
