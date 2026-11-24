package auth

import (
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/x509"
	"encoding/json"
	"encoding/pem"
	"errors"
	"log/slog"
	"slices"
	"strings"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

const (
	JobTokenIssuer   = "pl-assistant"
	JobTokenAudience = "pl-domain-mcp"
	jobTokenLeeway   = 30 * time.Second
	toolsCallMethod  = "tools/call"
	bearerPrefix     = "bearer "
)

var errJobTokenRejected = errors.New("job token rejected")

type JobClaims struct {
	PersonPK       string   `json:"person_pk"`
	AthletePK      string   `json:"athlete_pk"`
	ConversationID string   `json:"conversation_id"`
	WorkflowID     string   `json:"workflow_id"`
	Scope          []string `json:"scope"`
	jwt.RegisteredClaims
}

type Presented struct {
	Authorization string
	Person        string
	Athlete       string
	Source        string
}

type JobVerifier struct {
	key *ecdsa.PublicKey
	log *slog.Logger
	now func() time.Time
}

func NewJobVerifier(publicKeyPEM string, log *slog.Logger) *JobVerifier {
	verifier := &JobVerifier{log: log, now: time.Now}
	if strings.TrimSpace(publicKeyPEM) == "" {
		return verifier
	}
	verifier.key = parseP256PublicKey(publicKeyPEM)
	if verifier.key == nil {
		log.Error("job token public key unusable; bearer tokens denied")
	}
	return verifier
}

func parseP256PublicKey(publicKeyPEM string) *ecdsa.PublicKey {
	block, _ := pem.Decode([]byte(publicKeyPEM))
	if block == nil {
		return nil
	}
	parsed, err := x509.ParsePKIXPublicKey(block.Bytes)
	if err != nil {
		return nil
	}
	key, ok := parsed.(*ecdsa.PublicKey)
	if !ok || key.Curve != elliptic.P256() {
		return nil
	}
	return key
}

func bearerToken(authorization string) (string, bool) {
	trimmed := strings.TrimSpace(authorization)
	if len(trimmed) < len(bearerPrefix) || !strings.EqualFold(trimmed[:len(bearerPrefix)], bearerPrefix) {
		return "", false
	}
	return strings.TrimSpace(trimmed[len(bearerPrefix):]), true
}

func toolName(method string, params json.RawMessage) string {
	if method != toolsCallMethod {
		return ""
	}
	var call struct {
		Name string `json:"name"`
	}
	_ = json.Unmarshal(params, &call)
	return call.Name
}

func (v *JobVerifier) Resolve(presented Presented, method string, params json.RawMessage) (Caller, bool, error) {
	token, isBearer := bearerToken(presented.Authorization)
	if !isBearer {
		return Caller{Person: presented.Person, Athlete: presented.Athlete, Source: presented.Source}, false, nil
	}
	operation := toolName(method, params)
	if presented.Person != "" || presented.Athlete != "" {
		v.audit("", "", operation, "deny", "identity headers combined with bearer token")
		return Caller{}, true, errJobTokenRejected
	}
	claims, err := v.verify(token)
	if err != nil {
		v.audit("", "", operation, "deny", err.Error())
		return Caller{}, true, errJobTokenRejected
	}
	if method == toolsCallMethod && !slices.Contains(claims.Scope, operation) {
		v.audit(claims.ID, claims.PersonPK, operation, "deny", "operation outside token scope")
		return Caller{}, true, errJobTokenRejected
	}
	v.audit(claims.ID, claims.PersonPK, operation, "accept", "")
	return Caller{Person: claims.PersonPK, Athlete: claims.AthletePK}, true, nil
}

func (v *JobVerifier) verify(token string) (*JobClaims, error) {
	if v.key == nil {
		return nil, errors.New("token authentication disabled")
	}
	claims := &JobClaims{}
	_, err := jwt.ParseWithClaims(token, claims, func(*jwt.Token) (any, error) { return v.key, nil },
		jwt.WithValidMethods([]string{jwt.SigningMethodES256.Alg()}),
		jwt.WithIssuer(JobTokenIssuer),
		jwt.WithAudience(JobTokenAudience),
		jwt.WithExpirationRequired(),
		jwt.WithLeeway(jobTokenLeeway),
		jwt.WithTimeFunc(v.now),
	)
	if err != nil {
		return nil, err
	}
	if claims.ID == "" || claims.PersonPK == "" || claims.AthletePK == "" {
		return nil, errors.New("required claim missing")
	}
	return claims, nil
}

func (v *JobVerifier) audit(jti, person, operation, decision, reason string) {
	v.log.Info("job_token", "jti", jti, "person_pk", person, "operation", operation, "decision", decision, "reason", reason)
}

func IsJobTokenRejection(err error) bool {
	return errors.Is(err, errJobTokenRejected)
}
