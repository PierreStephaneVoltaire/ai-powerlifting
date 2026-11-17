package token

import (
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/x509"
	"encoding/hex"
	"encoding/pem"
	"errors"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

const (
	Issuer   = "pl-assistant"
	Audience = "pl-domain-mcp"
)

type Claims struct {
	PersonPK       string   `json:"person_pk"`
	AthletePK      string   `json:"athlete_pk"`
	ConversationID string   `json:"conversation_id"`
	WorkflowID     string   `json:"workflow_id"`
	Scope          []string `json:"scope"`
	jwt.RegisteredClaims
}

type Subject struct {
	PersonPK       string
	AthletePK      string
	ConversationID string
	WorkflowID     string
	Scope          []string
}

type Issued struct {
	Token     string
	JTI       string
	ExpiresAt time.Time
}

type Signer struct {
	key *ecdsa.PrivateKey
	ttl time.Duration
	now func() time.Time
}

func ParsePrivateKey(pemText string) (*ecdsa.PrivateKey, error) {
	block, _ := pem.Decode([]byte(pemText))
	if block == nil {
		return nil, errors.New("private key is not PEM")
	}
	if parsed, err := x509.ParsePKCS8PrivateKey(block.Bytes); err == nil {
		key, ok := parsed.(*ecdsa.PrivateKey)
		if !ok || key.Curve != elliptic.P256() {
			return nil, errors.New("private key must be ECDSA P-256")
		}
		return key, nil
	}
	key, err := x509.ParseECPrivateKey(block.Bytes)
	if err != nil {
		return nil, err
	}
	if key.Curve != elliptic.P256() {
		return nil, errors.New("private key must be ECDSA P-256")
	}
	return key, nil
}

func NewSigner(pemText string, ttl time.Duration) (*Signer, error) {
	key, err := ParsePrivateKey(pemText)
	if err != nil {
		return nil, err
	}
	return &Signer{key: key, ttl: ttl, now: time.Now}, nil
}

func (i *Signer) Mint(subject Subject) (Issued, error) {
	if subject.PersonPK == "" || subject.AthletePK == "" || len(subject.Scope) == 0 {
		return Issued{}, errors.New("subject requires person, athlete and scope")
	}
	raw := make([]byte, 16)
	if _, err := rand.Read(raw); err != nil {
		return Issued{}, err
	}
	now := i.now()
	expires := now.Add(i.ttl)
	jti := hex.EncodeToString(raw)
	claims := Claims{
		PersonPK:       subject.PersonPK,
		AthletePK:      subject.AthletePK,
		ConversationID: subject.ConversationID,
		WorkflowID:     subject.WorkflowID,
		Scope:          subject.Scope,
		RegisteredClaims: jwt.RegisteredClaims{
			Issuer:    Issuer,
			Audience:  jwt.ClaimStrings{Audience},
			IssuedAt:  jwt.NewNumericDate(now),
			ExpiresAt: jwt.NewNumericDate(expires),
			ID:        jti,
		},
	}
	signed, err := jwt.NewWithClaims(jwt.SigningMethodES256, claims).SignedString(i.key)
	if err != nil {
		return Issued{}, err
	}
	return Issued{Token: signed, JTI: jti, ExpiresAt: expires}, nil
}

func (i *Signer) PublicKey() *ecdsa.PublicKey {
	return &i.key.PublicKey
}
