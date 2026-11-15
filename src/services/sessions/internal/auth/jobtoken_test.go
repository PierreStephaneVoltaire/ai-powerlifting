package auth

import (
	"bytes"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/x509"
	"encoding/json"
	"encoding/pem"
	"io"
	"log/slog"
	"strings"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

var fixedNow = time.Date(2026, 11, 15, 12, 0, 0, 0, time.UTC)

type signer struct {
	key *ecdsa.PrivateKey
	pem string
}

func newSigner(t *testing.T) signer {
	t.Helper()
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	der, err := x509.MarshalPKIXPublicKey(&key.PublicKey)
	if err != nil {
		t.Fatal(err)
	}
	return signer{key: key, pem: string(pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: der}))}
}

func validClaims() JobClaims {
	return JobClaims{
		PersonPK: "person-1", AthletePK: "athlete-1", ConversationID: "c", WorkflowID: "w",
		Scope: []string{"session_list"},
		RegisteredClaims: jwt.RegisteredClaims{
			Issuer: JobTokenIssuer, Audience: jwt.ClaimStrings{JobTokenAudience}, ID: "jti-1",
			ExpiresAt: jwt.NewNumericDate(fixedNow.Add(5 * time.Minute)),
		},
	}
}

func (s signer) token(t *testing.T, claims JobClaims) string {
	t.Helper()
	signed, err := jwt.NewWithClaims(jwt.SigningMethodES256, claims).SignedString(s.key)
	if err != nil {
		t.Fatal(err)
	}
	return signed
}

func verifierFor(publicKey string, logs io.Writer) *JobVerifier {
	verifier := NewJobVerifier(publicKey, slog.New(slog.NewTextHandler(logs, nil)))
	verifier.now = func() time.Time { return fixedNow }
	return verifier
}

func callParams(name string) json.RawMessage {
	return json.RawMessage(`{"name":"` + name + `","arguments":{}}`)
}

func resolve(verifier *JobVerifier, token string, method string, name string) (Caller, bool, error) {
	return verifier.Resolve(Presented{Authorization: "Bearer " + token}, method, callParams(name))
}

func TestHappyPathTakesIdentityFromToken(t *testing.T) {
	signing := newSigner(t)
	var logs bytes.Buffer
	caller, bearer, err := resolve(verifierFor(signing.pem, &logs), signing.token(t, validClaims()), "tools/call", "session_list")
	if err != nil || !bearer {
		t.Fatalf("bearer=%v err=%v", bearer, err)
	}
	if caller.Person != "person-1" || caller.Athlete != "athlete-1" || caller.Source != "" {
		t.Fatalf("caller %+v", caller)
	}
	for _, want := range []string{"jti=jti-1", "person_pk=person-1", "operation=session_list", "decision=accept"} {
		if !strings.Contains(logs.String(), want) {
			t.Errorf("audit line missing %q: %s", want, logs.String())
		}
	}
}

func TestRejectedTokens(t *testing.T) {
	signing := newSigner(t)
	other := newSigner(t)
	mutate := func(change func(*JobClaims)) string {
		claims := validClaims()
		change(&claims)
		return signing.token(t, claims)
	}
	hmacToken, err := jwt.NewWithClaims(jwt.SigningMethodHS256, validClaims()).SignedString([]byte(signing.pem))
	if err != nil {
		t.Fatal(err)
	}
	noneToken, err := jwt.NewWithClaims(jwt.SigningMethodNone, validClaims()).SignedString(jwt.UnsafeAllowNoneSignatureType)
	if err != nil {
		t.Fatal(err)
	}
	cases := map[string]string{
		"forged signature": other.token(t, validClaims()),
		"expired":          mutate(func(c *JobClaims) { c.ExpiresAt = jwt.NewNumericDate(fixedNow.Add(-time.Minute)) }),
		"no expiry":        mutate(func(c *JobClaims) { c.ExpiresAt = nil }),
		"wrong audience":   mutate(func(c *JobClaims) { c.Audience = jwt.ClaimStrings{"other"} }),
		"wrong issuer":     mutate(func(c *JobClaims) { c.Issuer = "someone" }),
		"missing jti":      mutate(func(c *JobClaims) { c.ID = "" }),
		"missing person":   mutate(func(c *JobClaims) { c.PersonPK = "" }),
		"missing athlete":  mutate(func(c *JobClaims) { c.AthletePK = "" }),
		"alg none":         noneToken,
		"hs256 confusion":  hmacToken,
		"garbage":          "not-a-jwt",
	}
	for name, token := range cases {
		var logs bytes.Buffer
		if _, bearer, err := resolve(verifierFor(signing.pem, &logs), token, "tools/call", "session_list"); err == nil || !bearer || !IsJobTokenRejection(err) {
			t.Errorf("%s: bearer=%v err=%v", name, bearer, err)
		}
		if !strings.Contains(logs.String(), "decision=deny") {
			t.Errorf("%s: no deny audit line", name)
		}
	}
}

func TestExpiryHonoursSmallLeeway(t *testing.T) {
	signing := newSigner(t)
	claims := validClaims()
	claims.ExpiresAt = jwt.NewNumericDate(fixedNow.Add(-10 * time.Second))
	if _, _, err := resolve(verifierFor(signing.pem, io.Discard), signing.token(t, claims), "tools/call", "session_list"); err != nil {
		t.Fatalf("within leeway rejected: %v", err)
	}
}

func TestOperationOutsideScopeDenied(t *testing.T) {
	signing := newSigner(t)
	var logs bytes.Buffer
	_, _, err := resolve(verifierFor(signing.pem, &logs), signing.token(t, validClaims()), "tools/call", "session_delete")
	if !IsJobTokenRejection(err) {
		t.Fatalf("err=%v", err)
	}
	if !strings.Contains(logs.String(), "jti=jti-1") || !strings.Contains(logs.String(), "decision=deny") {
		t.Errorf("audit: %s", logs.String())
	}
}

func TestDiscoveryMethodsNeedValidTokenButNoScope(t *testing.T) {
	signing := newSigner(t)
	if _, _, err := resolve(verifierFor(signing.pem, io.Discard), signing.token(t, validClaims()), "tools/list", ""); err != nil {
		t.Fatal(err)
	}
}

func TestDisabledVerifierDeniesEveryBearer(t *testing.T) {
	signing := newSigner(t)
	for _, key := range []string{"", "not a pem"} {
		if _, bearer, err := resolve(verifierFor(key, io.Discard), signing.token(t, validClaims()), "tools/call", "session_list"); !bearer || err == nil {
			t.Errorf("key %q accepted", key)
		}
	}
}

func TestBearerCannotCombineWithMeshIdentity(t *testing.T) {
	signing := newSigner(t)
	verifier := verifierFor(signing.pem, io.Discard)
	token := "Bearer " + signing.token(t, validClaims())
	for _, presented := range []Presented{{Authorization: token, Person: "other"}, {Authorization: token, Athlete: "other"}} {
		if _, _, err := verifier.Resolve(presented, "tools/call", callParams("session_list")); err == nil {
			t.Errorf("combined identity accepted: %+v", presented)
		}
	}
	caller, _, err := verifier.Resolve(Presented{Authorization: token, Source: "spiffe://x/sa/powerlifting-app-backend"}, "tools/call", callParams("session_list"))
	if err != nil || caller.IsBackend() {
		t.Fatalf("source principal must not carry over: %+v %v", caller, err)
	}
}

func TestMeshPathUnchangedWithoutBearer(t *testing.T) {
	verifier := verifierFor("", io.Discard)
	caller, bearer, err := verifier.Resolve(Presented{Person: "p", Athlete: "a", Source: "s"}, "tools/call", callParams("session_list"))
	if err != nil || bearer || caller != (Caller{Person: "p", Athlete: "a", Source: "s"}) {
		t.Fatalf("%+v %v %v", caller, bearer, err)
	}
}
