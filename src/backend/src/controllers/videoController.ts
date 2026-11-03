import { PutObjectCommand, S3Client } from '@aws-sdk/client-s3'
import { createReadStream, statSync } from 'fs'
import { invokeLambda } from '../utils/lambda'
import type { LiftProfileVideoAngle, SessionVideo, VideoLibraryItem, VideoSort } from '@powerlifting/types'

export interface VideoUploadPresign {
  video_id: string
  s3_key: string
  metadata: Record<string, string>
}

const videosBucket = process.env.VIDEOS_BUCKET || 'powerlifting-session-videos'
const s3Client = new S3Client({ region: process.env.AWS_REGION || 'ca-central-1' })

export async function uploadSessionVideo(
  pk: string,
  version: string,
  sessionDate: string,
  filePath: string,
  filename: string,
  mimeType: string,
  exerciseName?: string,
  setNumber?: number,
  notes?: string,
  idempotencyKey?: string,
  sessionId?: string,
  lift?: 'squat' | 'bench' | 'deadlift',
  angle?: LiftProfileVideoAngle,
  targetRevision?: number,
): Promise<SessionVideo> {
  const expectedSize = statSync(filePath).size
  const presign = await presignSessionVideo(pk, version, sessionDate, filename, mimeType, idempotencyKey, expectedSize, sessionId, lift, angle, targetRevision)
  await s3Client.send(new PutObjectCommand({
    Bucket: videosBucket,
    Key: presign.s3_key,
    Body: createReadStream(filePath),
    ContentType: mimeType,
    ContentLength: expectedSize,
    Metadata: presign.metadata,
  }))
  return confirmSessionVideo(pk, version, sessionDate, presign.video_id, presign.s3_key, exerciseName, setNumber, notes, undefined, idempotencyKey, sessionId, lift, angle, targetRevision)
}

export async function presignSessionVideo(
  pk: string,
  version: string,
  sessionDate: string,
  filename: string,
  mimeType: string,
  idempotencyKey?: string,
  expectedSize?: number,
  sessionId?: string,
  lift?: 'squat' | 'bench' | 'deadlift',
  angle?: LiftProfileVideoAngle,
  targetRevision?: number,
): Promise<VideoUploadPresign> {
  return (await invokeLambda('video_upload_presign', {
    pk,
    version,
    session_date: sessionDate,
    filename,
    mimetype: mimeType,
    idempotency_key: idempotencyKey,
    expected_size: expectedSize,
    session_id: sessionId,
    lift,
    angle,
    target_revision: targetRevision,
  })) as VideoUploadPresign
}

export async function confirmSessionVideo(
  pk: string,
  version: string,
  sessionDate: string,
  videoId: string,
  s3Key: string,
  exerciseName?: string,
  setNumber?: number,
  notes?: string,
  expectedSize?: number,
  idempotencyKey?: string,
  sessionId?: string,
  lift?: 'squat' | 'bench' | 'deadlift',
  angle?: LiftProfileVideoAngle,
  targetRevision?: number,
): Promise<SessionVideo> {
  return (await invokeLambda('video_upload_confirm', {
    pk,
    version,
    session_date: sessionDate,
    video_id: videoId,
    s3_key: s3Key,
    exercise_name: exerciseName,
    set_number: setNumber,
    notes,
    expected_size: expectedSize,
    idempotency_key: idempotencyKey,
    session_id: sessionId,
    lift,
    angle,
    target_revision: targetRevision,
  })) as SessionVideo
}

export async function resolveMedia(pk: string, key: string): Promise<string> {
  return String(await invokeLambda('video_media_resolve', { pk, s3_key: key }))
}

export async function removeSessionVideo(
  pk: string,
  version: string,
  sessionDate: string,
  videoId: string,
  sessionId?: string,
): Promise<void> {
  await invokeLambda('video_remove', {
    pk,
    version,
    session_date: sessionDate,
    video_id: videoId,
    session_id: sessionId,
  })
}

export async function getVideoLibrary(
  pk: string,
  version: string,
  exercise?: string,
  sort: VideoSort = 'newest',
): Promise<{ videos: VideoLibraryItem[]; exercises: string[] }> {
  return (await invokeLambda('video_library_get', {
    pk,
    version,
    exercise,
    sort,
  })) as { videos: VideoLibraryItem[]; exercises: string[] }
}

export async function updateSessionVideoMetadata(
  pk: string,
  version: string,
  sessionDate: string,
  videoId: string,
  updates: { exerciseName?: string; setNumber?: number; notes?: string },
  sessionId?: string,
): Promise<SessionVideo> {
  return (await invokeLambda('video_update_metadata', {
    pk,
    version,
    session_date: sessionDate,
    video_id: videoId,
    exercise_name: updates.exerciseName,
    set_number: updates.setNumber,
    notes: updates.notes,
    session_id: sessionId,
  })) as SessionVideo
}
