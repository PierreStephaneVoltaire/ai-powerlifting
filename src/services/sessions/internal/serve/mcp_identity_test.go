package serve

import (
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/x509"
	"encoding/pem"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/danielgtaylor/huma/v2"
	"github.com/danielgtaylor/huma/v2/adapters/humachi"
	"github.com/go-chi/chi/v5"
	"github.com/golang-jwt/jwt/v5"
	"powerlifting/sessions/internal/auth"
)

func TestMCPForwardsSignedIdentityAndEnforcesScope(t *testing.T) {
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	public, err := x509.MarshalPKIXPublicKey(&key.PublicKey)
	if err != nil {
		t.Fatal(err)
	}
	verifier := auth.NewJobVerifier(string(pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: public})), slog.New(slog.NewTextHandler(io.Discard, nil)))
	claims := auth.JobClaims{PersonPK: "person", AthletePK: "athlete", Scope: []string{"allowed"}, RegisteredClaims: jwt.RegisteredClaims{Issuer: auth.JobTokenIssuer, Audience: jwt.ClaimStrings{auth.JobTokenAudience}, ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Minute)), ID: "job"}}
	token, err := jwt.NewWithClaims(jwt.SigningMethodES256, claims).SignedString(key)
	if err != nil {
		t.Fatal(err)
	}
	router := chi.NewRouter()
	registerMCP(humachi.New(router, huma.DefaultConfig("test", "1")), nil, verifier)
	for _, test := range []struct {
		name, body, authorization, person string
		want                              int
	}{
		{"valid bearer", `{"jsonrpc":"2.0","id":1,"method":"ping"}`, "Bearer " + token, "", http.StatusOK},
		{"invalid bearer", `{"jsonrpc":"2.0","id":1,"method":"ping"}`, "Bearer invalid", "", http.StatusUnauthorized},
		{"mixed identity", `{"jsonrpc":"2.0","id":1,"method":"ping"}`, "Bearer " + token, "other", http.StatusUnauthorized},
		{"outside scope", `{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"forbidden"}}`, "Bearer " + token, "", http.StatusUnauthorized},
	} {
		t.Run(test.name, func(t *testing.T) {
			req := httptest.NewRequest(http.MethodPost, "/mcp", strings.NewReader(test.body))
			req.Header.Set("Content-Type", "application/json")
			req.Header.Set("Authorization", test.authorization)
			if test.person != "" {
				req.Header.Set("X-Person-Pk", test.person)
			}
			rec := httptest.NewRecorder()
			router.ServeHTTP(rec, req)
			if rec.Code != test.want {
				t.Fatalf("status %d: %s", rec.Code, rec.Body.String())
			}
		})
	}
}
