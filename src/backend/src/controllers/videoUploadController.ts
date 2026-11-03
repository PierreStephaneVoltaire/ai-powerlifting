import {
  AbortMultipartUploadCommand,
  CompleteMultipartUploadCommand,
  CreateMultipartUploadCommand,
  HeadObjectCommand,
  S3Client,
  UploadPartCommand,
} from '@aws-sdk/client-s3'
import type { Readable } from 'stream'
import { confirmSessionVideo, presignSessionVideo } from './videoController'
import { partCount, VIDEO_PART_BYTES, type UploadedPart } from '../utils/videoMultipart'
import type { LiftProfileVideoAngle, SessionVideo } from '@powerlifting/types'

const videosBucket = process.env.VIDEOS_BUCKET || 'powerlifting-session-videos'
const s3Client = new S3Client({ region: process.env.AWS_REGION || 'ca-central-1' })

export interface VideoUploadTarget {
  sessionId?: string
  lift?: 'squat' | 'bench' | 'deadlift'
  angle?: LiftProfileVideoAngle
  targetRevision?: number
  idempotencyKey?: string
}

export interface VideoUploadSession {
  videoId: string
  s3Key: string
  uploadId: string
  partSize: number
  partCount: number
}

export async function startVideoUpload(
  pk: string,
  version: string,
  sessionDate: string,
  filename: string,
  mimeType: string,
  size: number,
  target: VideoUploadTarget,
): Promise<VideoUploadSession> {
  const presign = await presignSessionVideo(
    pk, version, sessionDate, filename, mimeType, target.idempotencyKey, size,
    target.sessionId, target.lift, target.angle, target.targetRevision,
  )
  const created = await s3Client.send(new CreateMultipartUploadCommand({
    Bucket: videosBucket,
    Key: presign.s3_key,
    ContentType: mimeType,
    Metadata: presign.metadata,
  }))
  if (!created.UploadId) throw new Error('S3 did not return a multipart upload id')
  return {
    videoId: presign.video_id,
    s3Key: presign.s3_key,
    uploadId: created.UploadId,
    partSize: VIDEO_PART_BYTES,
    partCount: partCount(size),
  }
}

export async function uploadVideoPart(s3Key: string, uploadId: string, partNumber: number, body: Readable, contentLength: number): Promise<string> {
  const uploaded = await s3Client.send(new UploadPartCommand({
    Bucket: videosBucket,
    Key: s3Key,
    UploadId: uploadId,
    PartNumber: partNumber,
    Body: body,
    ContentLength: contentLength,
  }))
  if (!uploaded.ETag) throw new Error('S3 did not return a part ETag')
  return uploaded.ETag
}

async function objectExists(s3Key: string): Promise<boolean> {
  try {
    await s3Client.send(new HeadObjectCommand({ Bucket: videosBucket, Key: s3Key }))
    return true
  } catch {
    return false
  }
}

export async function completeVideoUpload(
  pk: string,
  version: string,
  sessionDate: string,
  videoId: string,
  s3Key: string,
  uploadId: string,
  parts: UploadedPart[],
  details: { exerciseName?: string; setNumber?: number; notes?: string },
  target: VideoUploadTarget,
): Promise<SessionVideo> {
  try {
    await s3Client.send(new CompleteMultipartUploadCommand({
      Bucket: videosBucket,
      Key: s3Key,
      UploadId: uploadId,
      MultipartUpload: { Parts: parts.map((part) => ({ PartNumber: part.partNumber, ETag: part.etag })) },
    }))
  } catch (err) {
    const alreadyCompleted = (err as { name?: string }).name === 'NoSuchUpload' && await objectExists(s3Key)
    if (!alreadyCompleted) throw err
  }
  return confirmSessionVideo(
    pk, version, sessionDate, videoId, s3Key, details.exerciseName, details.setNumber, details.notes,
    undefined, target.idempotencyKey, target.sessionId, target.lift, target.angle, target.targetRevision,
  )
}

export async function abortVideoUpload(s3Key: string, uploadId: string): Promise<void> {
  try {
    await s3Client.send(new AbortMultipartUploadCommand({ Bucket: videosBucket, Key: s3Key, UploadId: uploadId }))
  } catch (err) {
    if ((err as { name?: string }).name !== 'NoSuchUpload') throw err
  }
}
