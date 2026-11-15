package external

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/s3"
)

const discordCDN = "https://cdn.discordapp.com/avatars/"

type Discord struct {
	Token  string
	Client *http.Client
	Log    *slog.Logger
	Base   string
}

func NewDiscord(token string, log *slog.Logger) *Discord {
	return &Discord{Token: token, Client: &http.Client{Timeout: 3 * time.Second}, Log: log, Base: "https://discord.com/api/v10"}
}

func (d *Discord) Avatar(ctx context.Context, userID string) string {
	if d.Token == "" || userID == "" {
		return ""
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, d.Base+"/users/"+userID, nil)
	if err != nil {
		return ""
	}
	request.Header.Set("Authorization", "Bot "+d.Token)
	request.Header.Set("User-Agent", "powerlifting-profile")
	response, err := d.Client.Do(request)
	if err != nil {
		d.warn(err)
		return ""
	}
	defer response.Body.Close()
	if response.StatusCode >= http.StatusBadRequest {
		d.warn(fmt.Errorf("status %d", response.StatusCode))
		return ""
	}
	var user struct {
		Avatar string `json:"avatar"`
	}
	if err := json.NewDecoder(response.Body).Decode(&user); err != nil || user.Avatar == "" {
		return ""
	}
	extension := "png"
	if strings.HasPrefix(user.Avatar, "a_") {
		extension = "gif"
	}
	return discordCDN + userID + "/" + user.Avatar + "." + extension + "?size=256"
}

func (d *Discord) warn(err error) {
	if d.Log != nil {
		d.Log.Warn("discord avatar lookup failed", "error", err)
	}
}

type Analytics struct {
	URL    string
	Client *http.Client
	Log    *slog.Logger
}

func NewAnalytics(url string, log *slog.Logger) *Analytics {
	return &Analytics{URL: strings.TrimRight(url, "/"), Client: &http.Client{Timeout: 60 * time.Second}, Log: log}
}

func (a *Analytics) EstimatedMaxes(ctx context.Context, person, athlete string) map[string]any {
	if person == "" || athlete == "" {
		return nil
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, a.URL+"/operations/weekly_analysis", bytes.NewReader([]byte(`{"block":""}`)))
	if err != nil {
		return nil
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Person-Pk", person)
	request.Header.Set("X-Athlete-Pk", athlete)
	response, err := a.Client.Do(request)
	if err != nil {
		a.warn(err)
		return nil
	}
	defer response.Body.Close()
	body, _ := io.ReadAll(response.Body)
	if response.StatusCode >= http.StatusBadRequest {
		a.warn(fmt.Errorf("status %d", response.StatusCode))
		return nil
	}
	var report struct {
		CurrentMaxes map[string]any `json:"current_maxes"`
	}
	if err := json.Unmarshal(body, &report); err != nil {
		return nil
	}
	return report.CurrentMaxes
}

func (a *Analytics) warn(err error) {
	if a.Log != nil {
		a.Log.Warn("analytics estimated maxes unavailable", "error", err)
	}
}

type Avatars struct {
	Client *s3.Client
	Bucket string
}

func (a *Avatars) Put(ctx context.Context, key, contentType string, body []byte, metadata map[string]string) error {
	_, err := a.Client.PutObject(ctx, &s3.PutObjectInput{
		Bucket: aws.String(a.Bucket), Key: aws.String(key), Body: bytes.NewReader(body),
		ContentType: aws.String(contentType), Metadata: metadata,
	})
	return err
}

func (a *Avatars) Delete(ctx context.Context, key string) error {
	_, err := a.Client.DeleteObject(ctx, &s3.DeleteObjectInput{Bucket: aws.String(a.Bucket), Key: aws.String(key)})
	return err
}
