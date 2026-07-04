# Powerlifting backend → Fission refactor: progress log

---

## NEXT — Domain 11: Video (`videoController.ts`) [LAST priority]

**Status:** `videoController.ts` imports `db/dynamo` AND `services/sessionStore`.
Manages video metadata stored as an array on session items in `if-sessions` +
S3 uploads.

**User direction:** keep the actual S3 upload in the backend (binary I/O, not
DynamoDB logic), move the session-video-array PATCH to Fission.

**What needs to be done:**

1. Read `videoController.ts` + `routes/videos.ts` end-to-end.
2. Move session-video-array read/patch to Fission (extend `pl_sessions` or new
   `video_*` functions); keep S3 `PutObject` in the backend.
3. Rewrite `videoController.ts` — remove `db/dynamo` import; keep S3 client only.

**Once video is done, `db/dynamo.ts` itself can be deleted (no consumers remain).**
