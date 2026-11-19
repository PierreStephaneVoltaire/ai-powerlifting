# Startup indexing for private reference PDFs

Upload reference PDFs directly to a private, versioned S3 bucket outside the media CDN. On assistant startup, discover and index the PDFs automatically. The supplement assistant and the general prompt share the importer and PostgreSQL search implementation. Each searches its own collection.

| S3 prefix | Collection used at lookup |
| --- | --- |
| `references/supplements/` | Supplement guides for supplement recommendations |
| `references/federation-rules/<federation-id>/` | Rulebooks for the federation selected in the general prompt |

## Startup

1. Once PostgreSQL is ready, start a background scan. Use a PostgreSQL advisory lock per collection so replicas starting together share the work. Keep published documents searchable while a scan is running.
2. Walk the paginated S3 version listing under the configured prefix. Consider only current, non-deleted PDF objects. Compare each object's key and opaque S3 version ID with the published version in a durable document manifest. An empty prefix with no indexed documents finishes immediately. A matching version requires no download, text extraction or embedding.
3. For each missing or changed version, download that exact version to temporary storage. Extract text by page, split it into passages and embed in bounded batches. Publish the passages and update the manifest together only after the entire document succeeds. Discard temporary files. A failed replacement leaves the last complete version searchable and the new version eligible for retry. Retry transient errors with backoff. If the scanning replica exits, its lock releases and another startup scan can resume from the manifest.
4. After successfully listing the entire prefix, retire entries whose objects have been removed. A failed or partial listing cannot retire documents. Uploads after a completed scan are picked up on the next startup.

Keep document versions, passages and vectors in a dedicated reference schema in the existing PostgreSQL/pgvector installation. The manifest is the record of what was indexed and survives pod restarts and cache eviction. Registering another collection requires a prefix and a lookup scope. Indexing works a document at a time, so corpus size does not determine pod memory requirements.

## Lookup

Callers select the collection before text or vector ranking. For rulebook questions the general prompt also supplies the federation ID. When the federation is ambiguous, resolve it before answering. Preserve the rulebook edition and effective date where available so a meet-date question can use the applicable rules.

For supplement advice, run guide lookup before drafting the answer or delegating to the web model. Answer from relevant passages. If the guide covers only part of the question, send only the unresolved part to web search. Respect a request to skip browsing.

The reference reader uses passages inside a single activity and returns a paraphrased finding. Keep raw passages out of conversation history, conversation embeddings, workflow checkpoints, caches and prompt logs. Use model endpoints configured accordingly for both embedding and reading. The original PDFs stay private to ingestion.

## Acceptance

- Start with an empty prefix, then upload two synthetic PDFs and restart. Both become searchable. Restart again and verify zero PDF downloads and zero embedding calls.
- Replace one PDF and start multiple replicas. Only the replacement is imported once. Interrupt that import and verify the old complete version remains readable until a retry publishes the replacement.
- Give a synthetic guide and two federations' rulebooks overlapping terminology. Verify supplement lookup retrieves only the guide and a general-prompt lookup retrieves only the requested federation's rulebook.
- For direct and delegated supplement questions, a guide hit makes zero web calls, partial coverage sends only the gap, and a miss attempts guide lookup before web fallback.
- Verify a unique raw passage from a synthetic PDF appears in the reference index and stays out of conversation storage, workflow checkpoints, caches and request logs.

## Operator uploads

The private, versioned bucket is `powerlifting-reference-documents-429310424269-ca-central-1`. Upload supplement guides under `references/supplements/` and rulebooks under `references/federation-rules/<federation-id>/`, using the federation ID used by the portal. For rulebooks, supply S3 object metadata `edition` and `effective-date` (ISO `YYYY-MM-DD`) when known. Use a distinct object key for each historical edition that should remain searchable. Set `FEDERATION_ID` to the portal federation ID before running:

```sh
aws s3 cp rulebook.pdf s3://powerlifting-reference-documents-429310424269-ca-central-1/references/federation-rules/"$FEDERATION_ID"/rulebook.pdf --metadata edition=2026,effective-date=2026-01-01
```

After uploads, replacements, or deletions, restart the assistant deployment to trigger a scan:

```sh
kubectl -n powerlifting rollout restart deployment/pl-assistant
```

The assistant uses the existing `pl-aws-credentials` secret. The AWS scope grants the shared `powerlifting-pods` identity read-only access to the two reference prefixes. Apply the AWS scope before the Kubernetes app scope so the assistant can index the bucket on startup.
