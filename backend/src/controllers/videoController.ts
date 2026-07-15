import { v4 as uuidv4 } from 'uuid'
import { S3Client, DeleteObjectCommand } from '@aws-sdk/client-s3'
import { Upload } from '@aws-sdk/lib-storage'
import { AppError } from '../middleware/errorHandler'
import { invokeLambda } from '../utils/lambda'
import { listSessions, patchSessionByDate, transformVideo } from '../services/sessionStore'
import { sortVideos } from '../utils/videoSort'
import type { Session, SessionVideo, VideoLibraryItem, VideoSort } from '@powerlifting/types'

const S3_BUCKET = process.env.VIDEOS_BUCKET || 'powerlifting-session-videos'
const S3_REGION = process.env.AWS_REGION || 'ca-central-1'

const s3Client = new S3Client({
  region: S3_REGION,
  credentials: process.env.AWS_ACCESS_KEY_ID && process.env.AWS_SECRET_ACCESS_KEY
    ? {
        accessKeyId: process.env.AWS_ACCESS_KEY_ID,
        secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY,
      }
    : undefined,
})

export async function uploadSessionVideo(
  pk: string,
  version: string,
  sessionDate: string,
  file: Buffer,
  filename: string,
  mimeType: string,
  exerciseName?: string,
  setNumber?: number,
  notes?: string
): Promise<SessionVideo> {
  const programSk = '' // Fission resolves current internally
  const session = (await listSessions(pk, programSk)).find(s => s.date === sessionDate)
  if (!session) {
    throw new AppError(`Session with date ${sessionDate} not found`, 404)
  }

  const videoId = uuidv4()
  const extension = filename.split('.').pop() || 'mp4'
  const s3Key = `videos/${sessionDate}/${videoId}.${extension}`

  try {
    const upload = new Upload({
      client: s3Client,
      params: {
        Bucket: S3_BUCKET,
        Key: s3Key,
        Body: file,
        ContentType: mimeType,
        Metadata: {
          video_id: videoId,
          session_date: sessionDate,
          pk,
          sk: programSk,
        },
      },
    })

    await upload.done()
  } catch (err) {
    throw new AppError(`Failed to upload video to storage: ${String(err)}`, 500)
  }

  const video: SessionVideo = {
    video_id: videoId,
    s3_key: s3Key,
    ...(exerciseName !== undefined && { exercise_name: exerciseName }),
    ...(setNumber !== undefined && { set_number: setNumber }),
    ...(notes !== undefined && { notes }),
    uploaded_at: new Date().toISOString(),
    thumbnail_status: 'pending',
  }

  await patchSessionByDate(pk, programSk, sessionDate, {
    videos: [...(session.videos || []), video],
  } as Partial<Session>)

  return transformVideo(video)
}

export async function removeSessionVideo(
  pk: string,
  version: string,
  sessionDate: string,
  videoId: string
): Promise<void> {
  const programSk = ''
  const session = (await listSessions(pk, programSk)).find(s => s.date === sessionDate)
  if (!session) {
    throw new AppError(`Session with date ${sessionDate} not found`, 404)
  }

  if (!session.videos) {
    throw new AppError(`Session has no videos`, 404)
  }

  const video = session.videos.find(v => v.video_id === videoId)

  if (!video) {
    throw new AppError(`Video ${videoId} not found`, 404)
  }

  const deletePromises: Promise<unknown>[] = [
    s3Client.send(new DeleteObjectCommand({ Bucket: S3_BUCKET, Key: video.s3_key })),
  ]

  if (video.thumbnail_s3_key) {
    deletePromises.push(
      s3Client.send(new DeleteObjectCommand({ Bucket: S3_BUCKET, Key: video.thumbnail_s3_key }))
    )
  }

  await Promise.all(deletePromises)

  const videos = session.videos.filter(v => v.video_id !== videoId)
  await patchSessionByDate(pk, programSk, sessionDate, {
    videos: videos.length > 0 ? videos : undefined,
  } as Partial<Session>)
}

export async function updateVideoThumbnail(
  pk: string,
  version: string,
  sessionDate: string,
  videoId: string,
  thumbnailUrl: string,
  thumbnailS3Key: string,
  status: 'ready' | 'failed'
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
  sort: VideoSort = 'newest'
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
  updates: { exerciseName?: string; setNumber?: number; notes?: string }
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
