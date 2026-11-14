package httpapi

import (
	"encoding/json"
	"net/http"

	"powerlifting/prompt-cache/internal/lookup"
)

const maxBodyBytes = 32 << 20

type API struct{ Service lookup.Service }

func (a API) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", func(w http.ResponseWriter, _ *http.Request) {
		write(w, http.StatusOK, map[string]string{"status": "ok"})
	})
	mux.HandleFunc("POST /lookup", a.lookup)
	mux.HandleFunc("POST /store", a.store)
	return mux
}

func (a API) lookup(w http.ResponseWriter, r *http.Request) {
	var query lookup.Query
	if !read(w, r, &query) {
		return
	}
	write(w, http.StatusOK, a.Service.Lookup(r.Context(), query))
}

func (a API) store(w http.ResponseWriter, r *http.Request) {
	var save lookup.Save
	if !read(w, r, &save) {
		return
	}
	id, err := a.Service.Store(r.Context(), save)
	if err != nil {
		write(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	write(w, http.StatusOK, map[string]string{"entry_id": id})
}

func read(w http.ResponseWriter, r *http.Request, target any) bool {
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, maxBodyBytes)).Decode(target); err != nil {
		write(w, http.StatusBadRequest, map[string]string{"error": "invalid JSON body"})
		return false
	}
	return true
}

func write(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}
