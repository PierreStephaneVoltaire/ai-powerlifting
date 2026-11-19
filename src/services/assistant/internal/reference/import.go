package reference

import (
	"context"
	"errors"
	"fmt"
	"io"
	"log"
	"os"
	"strings"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/jackc/pgx/v5"
	pdf "github.com/ledongthuc/pdf"
)

const referenceLockSQL = `SELECT pg_advisory_lock(hashtextextended('assistant-reference:' || $1, 0))`

func (s *Store) bootstrap(ctx context.Context) error {
	tx, err := s.config.Pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock(hashtextextended('assistant-reference-bootstrap', 0))`); err != nil {
		return err
	}
	statements := []string{
		`CREATE SCHEMA IF NOT EXISTS reference`,
		fmt.Sprintf(`CREATE TABLE IF NOT EXISTS reference.documents (
			collection TEXT NOT NULL,
			source_key TEXT NOT NULL,
			version_id TEXT NOT NULL,
			scope TEXT NOT NULL,
			edition TEXT NOT NULL DEFAULT '',
			effective_date DATE,
			indexed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
			PRIMARY KEY (collection, source_key)
		)`),
		fmt.Sprintf(`CREATE TABLE IF NOT EXISTS reference.passages (
			collection TEXT NOT NULL,
			source_key TEXT NOT NULL,
			version_id TEXT NOT NULL,
			scope TEXT NOT NULL,
			passage_no INTEGER NOT NULL,
			text TEXT NOT NULL,
			page INTEGER NOT NULL,
			edition TEXT NOT NULL DEFAULT '',
			effective_date DATE,
			embedding vector(%d) NOT NULL,
			PRIMARY KEY (collection, source_key, version_id, passage_no)
		)`, s.config.EmbedDim),
		`CREATE INDEX IF NOT EXISTS passages_scope_idx ON reference.passages (collection, scope)`,
	}
	for _, statement := range statements {
		if _, err := tx.Exec(ctx, statement); err != nil {
			return fmt.Errorf("reference schema: %w", err)
		}
	}
	return tx.Commit(ctx)
}

func retryBootstrap(ctx context.Context, bootstrap func(context.Context) error, backoff time.Duration) error {
	for {
		if err := ctx.Err(); err != nil {
			return err
		}
		if err := bootstrap(ctx); err == nil {
			return nil
		}
		if err := ctx.Err(); err != nil {
			return err
		}
		log.Print("reference schema bootstrap failed; retrying")
		timer := time.NewTimer(backoff)
		select {
		case <-ctx.Done():
			timer.Stop()
			return ctx.Err()
		case <-timer.C:
		}
		if backoff < time.Minute {
			backoff *= 2
			if backoff > time.Minute {
				backoff = time.Minute
			}
		}
	}
}

func (s *Store) retryCollection(ctx context.Context, collection Collection) {
	backoff := time.Second
	for ctx.Err() == nil {
		err := s.scanCollection(ctx, collection)
		if ctx.Err() != nil {
			return
		}
		if err == nil {
			return
		}
		log.Printf("reference scan failed collection=%s; retrying", collection.Name)
		timer := time.NewTimer(backoff)
		select {
		case <-ctx.Done():
			timer.Stop()
			return
		case <-timer.C:
		}
		if backoff < time.Minute {
			backoff *= 2
			if backoff > time.Minute {
				backoff = time.Minute
			}
		}
	}
}

func (s *Store) scanCollection(ctx context.Context, collection Collection) error {
	conn, err := pgx.ConnectConfig(ctx, s.config.Pool.Config().ConnConfig.Copy())
	if err != nil {
		return err
	}
	defer func() {
		closeCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = conn.Close(closeCtx)
	}()
	if _, err := conn.Exec(ctx, referenceLockSQL, collection.Name); err != nil {
		return err
	}
	defer func() {
		unlockCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_, _ = conn.Exec(unlockCtx, `SELECT pg_advisory_unlock(hashtextextended('assistant-reference:' || $1, 0))`, collection.Name)
	}()

	objects, err := s.currentPDFs(ctx, collection)
	if err != nil {
		return err
	}
	var failed bool
	for key, versionID := range objects {
		var published string
		err := s.config.Pool.QueryRow(ctx, `SELECT version_id FROM reference.documents WHERE collection=$1 AND source_key=$2`, collection.Name, key).Scan(&published)
		if err == nil && published == versionID {
			continue
		}
		if err != nil && !errors.Is(err, pgx.ErrNoRows) {
			return err
		}
		if err := s.importDocument(ctx, collection, key, versionID); err != nil {
			log.Printf("reference document failed collection=%s stage=%s", collection.Name, failureStage(err))
			failed = true
			continue
		}
	}
	if err := s.retireRemoved(ctx, collection, objects); err != nil {
		return err
	}
	if failed {
		return errors.New("one or more reference documents failed")
	}
	log.Printf("reference scan complete collection=%s documents=%d", collection.Name, len(objects))
	return nil
}

func (s *Store) currentPDFs(ctx context.Context, collection Collection) (map[string]string, error) {
	input := &s3.ListObjectVersionsInput{Bucket: aws.String(s.config.Bucket), Prefix: aws.String(collection.Prefix)}
	objects := map[string]string{}
	for {
		page, err := s.config.S3.ListObjectVersions(ctx, input)
		if err != nil {
			return nil, err
		}
		for _, version := range page.Versions {
			if aws.ToBool(version.IsLatest) && strings.HasSuffix(strings.ToLower(aws.ToString(version.Key)), ".pdf") {
				objects[aws.ToString(version.Key)] = aws.ToString(version.VersionId)
			}
		}
		if !aws.ToBool(page.IsTruncated) {
			break
		}
		if page.NextKeyMarker == nil || (aws.ToString(page.NextKeyMarker) == aws.ToString(input.KeyMarker) && aws.ToString(page.NextVersionIdMarker) == aws.ToString(input.VersionIdMarker)) {
			return nil, errors.New("invalid S3 pagination markers")
		}
		input.KeyMarker, input.VersionIdMarker = page.NextKeyMarker, page.NextVersionIdMarker
	}
	return objects, nil
}

type extractedPassage struct {
	text string
	page int
}

type importError struct{ stage string }

func (e importError) Error() string { return e.stage }
func failureStage(err error) string {
	var stage importError
	if errors.As(err, &stage) {
		return stage.stage
	}
	return "database"
}

func (s *Store) importDocument(ctx context.Context, collection Collection, key, versionID string) (result error) {
	stage := "download"
	defer func() {
		if result != nil {
			result = importError{stage: stage}
		}
	}()
	response, err := s.config.S3.GetObject(ctx, &s3.GetObjectInput{Bucket: aws.String(s.config.Bucket), Key: aws.String(key), VersionId: aws.String(versionID)})
	if err != nil {
		return err
	}
	defer response.Body.Close()
	tmp, err := os.CreateTemp("", "nolift-reference-*.pdf")
	if err != nil {
		return err
	}
	path := tmp.Name()
	defer os.Remove(path)
	if _, err := io.Copy(tmp, response.Body); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}

	stage = "scope"
	edition := response.Metadata["edition"]
	effective, _ := time.Parse("2006-01-02", response.Metadata["effective-date"])
	var effectiveDate any
	if !effective.IsZero() {
		effectiveDate = effective
	}
	scope, err := scopeForKey(collection, key)
	if err != nil {
		return err
	}
	stage = "database"
	tx, err := s.config.Pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(context.Background())
	if _, err = tx.Exec(ctx, `DELETE FROM reference.passages WHERE collection=$1 AND source_key=$2`, collection.Name, key); err != nil {
		return err
	}
	count := 0
	passages := make([]extractedPassage, 0, s.config.BatchSize)
	flush := func() error {
		if len(passages) == 0 {
			return nil
		}
		inputs := make([]string, len(passages))
		for i, passage := range passages {
			inputs[i] = passage.text
		}
		stage = "embedding"
		vectors, err := s.config.EmbedBatch(ctx, inputs)
		if err != nil {
			return err
		}
		if len(vectors) != len(passages) {
			return errors.New("embedding batch has wrong length")
		}
		batch := &pgx.Batch{}
		for i, passage := range passages {
			if err := validateVector(vectors[i], s.config.EmbedDim); err != nil {
				return err
			}
			batch.Queue(`INSERT INTO reference.passages (collection,source_key,version_id,scope,passage_no,text,page,edition,effective_date,embedding) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::vector)`, collection.Name, key, versionID, scope, count+i, passage.text, passage.page, edition, effectiveDate, vectorLiteral(vectors[i]))
		}
		stage = "database"
		results := tx.SendBatch(ctx, batch)
		for range passages {
			if _, err := results.Exec(); err != nil {
				_ = results.Close()
				return err
			}
		}
		if err := results.Close(); err != nil {
			return err
		}
		count += len(passages)
		passages = passages[:0]
		return nil
	}
	stage = "extraction"
	err = extractPages(path, func(pageNo int, pageText string) error {
		for _, text := range splitPassages(pageText, passageSize, passageOverlap) {
			passages = append(passages, extractedPassage{text: text, page: pageNo})
			if len(passages) == s.config.BatchSize {
				if err := flush(); err != nil {
					return err
				}
			}
		}
		stage = "extraction"
		return nil
	})
	if err == nil {
		err = flush()
	}
	if err != nil {
		return err
	}
	if count == 0 {
		return errors.New("PDF contains no extractable text")
	}
	stage = "database"
	_, err = tx.Exec(ctx, `INSERT INTO reference.documents (collection,source_key,version_id,scope,edition,effective_date) VALUES ($1,$2,$3,$4,$5,$6) ON CONFLICT (collection,source_key) DO UPDATE SET version_id=EXCLUDED.version_id,scope=EXCLUDED.scope,edition=EXCLUDED.edition,effective_date=EXCLUDED.effective_date,indexed_at=now()`, collection.Name, key, versionID, scope, edition, effectiveDate)
	if err != nil {
		return err
	}
	if err = tx.Commit(ctx); err == nil {
		log.Printf("reference document indexed collection=%s passages=%d", collection.Name, count)
	}
	return err
}

func extractPages(path string, consume func(int, string) error) (err error) {
	defer func() {
		if recover() != nil {
			err = errors.New("malformed PDF")
		}
	}()
	file, reader, err := pdf.Open(path)
	if err != nil {
		return err
	}
	defer file.Close()
	for pageNo := 1; pageNo <= reader.NumPage(); pageNo++ {
		text, err := reader.Page(pageNo).GetPlainText(nil)
		if err != nil {
			return fmt.Errorf("extract page %d: %w", pageNo, err)
		}
		if err := consume(pageNo, text); err != nil {
			return err
		}
	}
	return nil
}

func splitPassages(text string, size, overlap int) []string {
	text = strings.Join(strings.Fields(text), " ")
	if text == "" {
		return nil
	}
	runes := []rune(text)
	var passages []string
	for start := 0; start < len(runes); {
		end := start + size
		if end >= len(runes) {
			passages = append(passages, string(runes[start:]))
			break
		}
		for boundary := end - 1; boundary > start+size/2; boundary-- {
			if runes[boundary] == ' ' {
				end = boundary
				break
			}
		}
		passages = append(passages, strings.TrimSpace(string(runes[start:end])))
		start = end - overlap
		for start < len(runes) && runes[start] == ' ' {
			start++
		}
	}
	return passages
}

func scopeForKey(collection Collection, key string) (string, error) {
	if collection.Scope != "federation:*" {
		return collection.Scope, nil
	}
	if !strings.HasPrefix(key, collection.Prefix) {
		return "", fmt.Errorf("federation rulebook key is outside its collection prefix: %s", key)
	}
	relative := strings.TrimPrefix(key, collection.Prefix)
	federation, _, found := strings.Cut(relative, "/")
	if !found || federation == "" {
		return "", fmt.Errorf("federation rulebook key has no federation ID: %s", key)
	}
	return "federation:" + federation, nil
}

func (s *Store) retireRemoved(ctx context.Context, collection Collection, objects map[string]string) error {
	rows, err := s.config.Pool.Query(ctx, `SELECT source_key FROM reference.documents WHERE collection=$1`, collection.Name)
	if err != nil {
		return err
	}
	var removed []string
	for rows.Next() {
		var key string
		if err := rows.Scan(&key); err != nil {
			rows.Close()
			return err
		}
		if _, ok := objects[key]; !ok {
			removed = append(removed, key)
		}
	}
	if err := rows.Err(); err != nil {
		rows.Close()
		return err
	}
	rows.Close()
	tx, err := s.config.Pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(context.Background())
	for _, key := range removed {
		if _, err := tx.Exec(ctx, `DELETE FROM reference.passages WHERE collection=$1 AND source_key=$2`, collection.Name, key); err != nil {
			return err
		}
		if _, err := tx.Exec(ctx, `DELETE FROM reference.documents WHERE collection=$1 AND source_key=$2`, collection.Name, key); err != nil {
			return err
		}
	}
	return tx.Commit(ctx)
}
