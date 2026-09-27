# ADR 0004 — Media delivery through the CDN

Date: 2026-09-26.

## Status

Accepted. Supersedes the media clause of ADR 0002 ("Revocation and expiry
affect the next operation, including reads of cached ... media") and the
"authorized `/api` reads, CloudFront disabled" delivery in ARCHITECTURE.md.

## Context

Every thumbnail and video byte was proxied through the backend with
`Cache-Control: no-store`, each request running the Profile access check, a
media registry lookup and a Program-wide Session scan before streaming from S3.
A profile grid with hundreds of Lift Videos issued hundreds of these at once;
the videos service ran out of memory and thumbnails failed intermittently.
Public profiles paid the same cost. Nothing was cacheable.

## Decision

The retained CloudFront distribution is enabled and is the only read path to
media bytes. S3 stays private behind Origin Access Control.

- Thumbnails (`thumbnails/*`) are not sensitive. They are served unsigned and
  cached as immutable; keys carry a processing revision, so a new thumbnail is
  a new URL. The browser loads them straight from the CDN.
- Full videos and every other key require a CloudFront signed URL. The
  backend authorizes once per play (`/api/videos/media/<key>`) and redirects
  to a canned-policy URL valid for 72 hours. Expiry is aligned to a daily
  boundary so the URL, and therefore browser and CDN caches, stay stable for a
  day.
- Budget media and profile avatars keep their authorized `/api` endpoints;
  the CDN refuses their unsigned requests.

The signing key pair is generated in the powerlifting Terraform stack,
registered as a CloudFront key group, and published through SSM for the
backend.

## Consequences

Revoking access to a full video takes effect when already-issued signed URLs
expire, at most 96 hours later, not on the next read. Thumbnails of any Athlete
are readable by anyone who knows the key. In exchange, grid rendering no longer
touches the backend, playback costs one authorization, and repeat views are
served from browser or edge cache.
