package token

import (
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/x509"
	"encoding/pem"
	"slices"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

func testKey(t *testing.T) (*ecdsa.PrivateKey, string) {
	t.Helper()
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	der, err := x509.MarshalPKCS8PrivateKey(key)
	if err != nil {
		t.Fatal(err)
	}
	return key, string(pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: der}))
}

func verify(raw string, key *ecdsa.PublicKey, now time.Time) (*Claims, error) {
	claims := &Claims{}
	_, err := jwt.ParseWithClaims(raw, claims, func(*jwt.Token) (any, error) { return key, nil },
		jwt.WithValidMethods([]string{jwt.SigningMethodES256.Alg()}),
		jwt.WithIssuer("pl-assistant"),
		jwt.WithAudience("pl-domain-mcp"),
		jwt.WithExpirationRequired(),
		jwt.WithLeeway(30*time.Second),
		jwt.WithTimeFunc(func() time.Time { return now }),
	)
	return claims, err
}

func subject() Subject {
	return Subject{PersonPK: "p1", AthletePK: "a1", ConversationID: "powerlifting:a1:web:p1:x", WorkflowID: "wf", Scope: []string{"session_get"}}
}

func TestMintedTokenSatisfiesVerifier(t *testing.T) {
	key, pemText := testKey(t)
	signer, err := NewSigner(pemText, 5*time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	issued, err := signer.Mint(subject())
	if err != nil {
		t.Fatal(err)
	}
	claims, err := verify(issued.Token, &key.PublicKey, time.Now())
	if err != nil {
		t.Fatal(err)
	}
	if claims.PersonPK != "p1" || claims.AthletePK != "a1" || claims.WorkflowID != "wf" || claims.ID == "" || claims.ID != issued.JTI || !slices.Equal(claims.Scope, []string{"session_get"}) {
		t.Fatalf("claims mismatch: %+v", claims)
	}
}

func TestTokenExpiresAndIsKeyBound(t *testing.T) {
	key, pemText := testKey(t)
	signer, _ := NewSigner(pemText, 5*time.Minute)
	issued, _ := signer.Mint(subject())
	if _, err := verify(issued.Token, &key.PublicKey, time.Now().Add(10*time.Minute)); err == nil {
		t.Fatal("expired token accepted")
	}
	other, _ := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if _, err := verify(issued.Token, &other.PublicKey, time.Now()); err == nil {
		t.Fatal("token verified under a different key")
	}
}

func TestMintRejectsIncompleteSubjectAndUniqueJTI(t *testing.T) {
	_, pemText := testKey(t)
	signer, _ := NewSigner(pemText, time.Minute)
	if _, err := signer.Mint(Subject{PersonPK: "p1"}); err == nil {
		t.Fatal("incomplete subject accepted")
	}
	first, _ := signer.Mint(subject())
	second, _ := signer.Mint(subject())
	if first.JTI == second.JTI {
		t.Fatal("jti repeated")
	}
}
