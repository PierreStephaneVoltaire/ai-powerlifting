package semantic

import (
	"context"
	"encoding/json"
	"fmt"
	"regexp"
	"strings"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

const (
	findTool  = "qdrant-find"
	storeTool = "qdrant-store"
)

var (
	collectionUnsafe = regexp.MustCompile(`[^A-Za-z0-9_-]`)
	metadataPattern  = regexp.MustCompile(`(?s)<metadata>(.*?)</metadata>`)
)

type Metadata struct {
	EntryID         string `json:"entry_id"`
	Date            string `json:"date"`
	AnalysisVersion string `json:"analysis_version"`
}

type MCP struct{ URL string }

func Collection(athlete, operation string) string {
	return "pc_" + collectionUnsafe.ReplaceAllString(athlete+"__"+operation, "_")
}

func (m MCP) call(ctx context.Context, tool string, arguments map[string]any) (*mcp.CallToolResult, error) {
	client := mcp.NewClient(&mcp.Implementation{Name: "pl-prompt-cache-api", Version: "1.0.0"}, nil)
	session, err := client.Connect(ctx, &mcp.StreamableClientTransport{Endpoint: m.URL, MaxRetries: -1}, nil)
	if err != nil {
		return nil, err
	}
	defer session.Close()
	result, err := session.CallTool(ctx, &mcp.CallToolParams{Name: tool, Arguments: arguments})
	if err != nil {
		return nil, err
	}
	if result.IsError {
		return nil, fmt.Errorf("%s failed", tool)
	}
	return result, nil
}

func (m MCP) Find(ctx context.Context, athlete, operation, query string) ([]Metadata, error) {
	result, err := m.call(ctx, findTool, map[string]any{"query": query, "collection_name": Collection(athlete, operation)})
	if err != nil {
		return nil, err
	}
	found := []Metadata{}
	for _, content := range result.Content {
		text, ok := content.(*mcp.TextContent)
		if !ok {
			continue
		}
		for _, match := range metadataPattern.FindAllStringSubmatch(text.Text, -1) {
			var metadata Metadata
			if err := json.Unmarshal([]byte(strings.TrimSpace(match[1])), &metadata); err == nil && metadata.EntryID != "" {
				found = append(found, metadata)
			}
		}
	}
	return found, nil
}

func (m MCP) Store(ctx context.Context, athlete, operation, text string, metadata Metadata) error {
	_, err := m.call(ctx, storeTool, map[string]any{"information": text, "collection_name": Collection(athlete, operation), "metadata": metadata})
	return err
}
