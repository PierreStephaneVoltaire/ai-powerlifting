import { GetObjectCommand, HeadObjectCommand, PutObjectCommand, S3Client } from '@aws-sdk/client-s3'
import { createReadStream } from 'fs'
import { invokeLambda } from '../utils/lambda'
import type { SessionVideo, VideoLibraryItem, VideoSort } from '@powerlifting/types'

export interface VideoUploadPresign {
  video_id: string
  s3_key: string
  upload_url: string
  upload_headers: Record<string, string>
  expires_in: number
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
): Promise<SessionVideo> {
  const presign = await presignSessionVideo(pk, version, sessionDate, filename, mimeType)
  const metadata = Object.fromEntries(
    Object.entries(presign.upload_headers)
      .filter(([key]) => key.toLowerCase().startsWith('x-amz-meta-'))
      .map(([key, value]) => [key.slice('x-amz-meta-'.length), value]),
  )
  await s3Client.send(new PutObjectCommand({
    Bucket: videosBucket,
    Key: presign.s3_key,
    Body: createReadStream(filePath),
    ContentType: mimeType,
    Metadata: metadata,
  }))
  return confirmSessionVideo(pk, version, sessionDate, presign.video_id, presign.s3_key, exerciseName, setNumber, notes)
}

export async function headMedia(key: string) {
  return s3Client.send(new HeadObjectCommand({ Bucket: videosBucket, Key: key }))
}

export async function getMedia(key: string, range?: string) {
  return s3Client.send(new GetObjectCommand({ Bucket: videosBucket, Key: key, ...(range ? { Range: range } : {}) }))
}

export async function presignSessionVideo(
  pk: string,
  version: string,
  sessionDate: string,
  filename: string,
  mimeType: string,
): Promise<VideoUploadPresign> {
  return (await invokeLambda('video_upload_presign', {
    pk,
    version,
    session_date: sessionDate,
    filename,
    mimetype: mimeType,
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
  })) as SessionVideo
}

export async function removeSessionVideo(
  pk: string,
  version: string,
  sessionDate: string,
  videoId: string,
): Promise<void> {
  await invokeLambda('video_remove', {
    pk,
    version,
    session_date: sessionDate,
    video_id: videoId,
  })
}

export async function updateVideoThumbnail(
  pk: string,
  version: string,
  sessionDate: string,
  videoId: string,
  _thumbnailUrl: string,
  thumbnailS3Key: string,
  status: 'ready' | 'failed',
): Promise<void> {
  await invokeLambda('video_update_thumbnail', {
    pk,
    version,
    session_date: sessionDate,
    video_id: videoId,
    thumbnail_s3_key: thumbnailS3Key,
    status,
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
): Promise<SessionVideo> {
  return (await invokeLambda('video_update_metadata', {
    pk,
    version,
    session_date: sessionDate,
    video_id: videoId,
    exercise_name: updates.exerciseName,
    set_number: updates.setNumber,
    notes: updates.notes,
  })) as SessionVideo
}
