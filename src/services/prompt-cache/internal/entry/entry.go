package entry

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"strings"
)

type Context struct {
	Date            string `json:"date"`
	AnalysisVersion string `json:"analysis_version"`
}

type Entry struct {
	ID        string          `json:"id"`
	Athlete   string          `json:"athlete"`
	Operation string          `json:"operation"`
	Request   json.RawMessage `json:"request"`
	Response  json.RawMessage `json:"response"`
	Context   Context         `json:"context"`
}

func Hash(request json.RawMessage) (string, error) {
	decoder := json.NewDecoder(bytes.NewReader(request))
	decoder.UseNumber()
	var value any
	if err := decoder.Decode(&value); err != nil {
		return "", err
	}
	var buffer bytes.Buffer
	encoder := json.NewEncoder(&buffer)
	encoder.SetEscapeHTML(false)
	if err := encoder.Encode(value); err != nil {
		return "", err
	}
	sum := sha256.Sum256(bytes.TrimSpace(buffer.Bytes()))
	return hex.EncodeToString(sum[:]), nil
}

func SearchableText(request json.RawMessage) string {
	var parsed struct {
		Messages []struct {
			Role    string          `json:"role"`
			Content json.RawMessage `json:"content"`
		} `json:"messages"`
	}
	if err := json.Unmarshal(request, &parsed); err != nil {
		return ""
	}
	parts := make([]string, 0, len(parsed.Messages))
	for _, message := range parsed.Messages {
		if message.Role == "system" {
			continue
		}
		var text string
		if err := json.Unmarshal(message.Content, &text); err == nil {
			parts = append(parts, text)
		} else {
			parts = append(parts, string(message.Content))
		}
	}
	return strings.Join(parts, "\n\n")
}
