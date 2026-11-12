package store

import (
	"bytes"
	"context"
	"errors"
	"sync"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/aws/aws-sdk-go-v2/service/s3/types"
)

var ErrNotFound = errors.New("object not found")

type Store interface {
	Get(ctx context.Context, key string) ([]byte, error)
	Put(ctx context.Context, key, contentType string, body []byte) error
}

type S3 struct {
	client *s3.Client
	bucket string
}

func NewS3(client *s3.Client, bucket string) *S3 {
	return &S3{client: client, bucket: bucket}
}

func (s *S3) Get(ctx context.Context, key string) ([]byte, error) {
	output, err := s.client.GetObject(ctx, &s3.GetObjectInput{Bucket: aws.String(s.bucket), Key: aws.String(key)})
	if err != nil {
		var missing *types.NoSuchKey
		if errors.As(err, &missing) {
			return nil, ErrNotFound
		}
		return nil, err
	}
	defer output.Body.Close()
	var buffer bytes.Buffer
	if _, err := buffer.ReadFrom(output.Body); err != nil {
		return nil, err
	}
	return buffer.Bytes(), nil
}

func (s *S3) Put(ctx context.Context, key, contentType string, body []byte) error {
	_, err := s.client.PutObject(ctx, &s3.PutObjectInput{
		Bucket:      aws.String(s.bucket),
		Key:         aws.String(key),
		Body:        bytes.NewReader(body),
		ContentType: aws.String(contentType),
	})
	return err
}

type Memory struct {
	mu      sync.Mutex
	Objects map[string][]byte
	Types   map[string]string
}

func NewMemory() *Memory {
	return &Memory{Objects: map[string][]byte{}, Types: map[string]string{}}
}

func (m *Memory) Get(_ context.Context, key string) ([]byte, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	body, ok := m.Objects[key]
	if !ok {
		return nil, ErrNotFound
	}
	return body, nil
}

func (m *Memory) Put(_ context.Context, key, contentType string, body []byte) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.Objects[key] = body
	m.Types[key] = contentType
	return nil
}
