package apperr

import (
	"encoding/json"
	"fmt"
	"net/http"
)

type Error struct {
	Status  int
	Code    string
	Message string
	detail  any
}

func (e *Error) Error() string { return e.Message }

func (e *Error) GetStatus() int { return e.Status }

func (e *Error) Detail() any {
	if e.detail != nil {
		return e.detail
	}
	return map[string]any{"code": e.Code, "message": e.Message}
}

func (e *Error) MarshalJSON() ([]byte, error) {
	return json.Marshal(map[string]any{"detail": e.Detail()})
}

func plain(status int, message string) *Error {
	return &Error{Status: status, Message: message, detail: message}
}

func UnknownOperation() *Error { return plain(http.StatusNotFound, "Unknown operation") }

func GenerationWithoutTurn() *Error {
	return plain(http.StatusForbidden, "Generation requires an active native turn")
}

func Forbidden(message string) *Error {
	return &Error{Status: http.StatusForbidden, Code: "forbidden", Message: message}
}

func AccessDenied(status int) *Error {
	if status < http.StatusBadRequest {
		status = http.StatusForbidden
	}
	return &Error{Status: status, Code: "forbidden", Message: "Access evaluation denied"}
}

func AccessUnavailable() *Error {
	return &Error{Status: http.StatusServiceUnavailable, Code: "access_unavailable", Message: "Permission service unavailable"}
}

func NestedWithoutExecution() *Error {
	return &Error{Status: http.StatusConflict, Code: "uncertain", Message: "Nested operation requires an active domain execution"}
}

func Uncertain(message string) *Error {
	return &Error{Status: http.StatusConflict, Code: "uncertain", Message: message}
}

func Validation(message string) *Error {
	return &Error{Status: http.StatusUnprocessableEntity, Code: "validation", Message: message}
}

func Body() *Error {
	message := "Request body must be a JSON object"
	return &Error{
		Status:  http.StatusUnprocessableEntity,
		Code:    "validation",
		Message: message,
		detail:  []any{map[string]any{"type": "dict_type", "loc": []string{"body"}, "msg": message}},
	}
}

func InvalidResult() *Error {
	return &Error{Status: http.StatusInternalServerError, Code: "invalid_result", Message: "Domain returned an invalid result"}
}

func NotFound(format string, args ...any) *Error {
	return &Error{Status: http.StatusNotFound, Code: "not_found", Message: fmt.Sprintf(format, args...)}
}

func Busy(message string) *Error {
	return &Error{Status: http.StatusTooManyRequests, Code: "busy", Message: message}
}

func ExecutionFailed(status int, message string) *Error {
	return &Error{Status: status, Code: "execution_failed", Message: message}
}

func Internal(message string) *Error {
	return &Error{Status: http.StatusInternalServerError, Code: "internal", Message: message}
}
