import { v4 as uuidv4 } from 'uuid'
import { GetCommand } from '@aws-sdk/lib-dynamodb'
import { S3Client, DeleteObjectCommand } from '@aws-sdk/client-s3'
import { Upload } from '@aws-sdk/lib-storage'
import { docClient, TABLE } from '../db/dynamo'
import { AppError } from '../middleware/errorHandler'
import { listSessions, patchSessionByDate } from '../services/sessionStore'
import type { Phase, Session, SessionVideo, VideoLibraryItem } from '@powerlifting/types'

const S3_BUCKET = process.env.VIDEOS_BUCKET || 'powerlifting-session-videos'
const S3_REGION = process.env.AWS_REGION || 'ca-central-1'
const SESSION_TABLE = process.env.IF_SESSIONS_TABLE_NAME || 'if-sessions'

const s3Client = new S3Client({
  region: S3_REGION,
  credentials: process.env.AWS_ACCESS_KEY_ID && process.env.AWS_SECRET_ACCESS_KEY
    ? {
        accessKeyId: process.env.AWS_ACCESS_KEY_ID,
        secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY,
      }
    : undefined,
})

function stripUndefined(obj: any): any {
  if (obj === null || typeof obj !== 'object') return obj
  if (Array.isArray(obj)) return obj.map(stripUndefined)
  const cleaned: any = {}
  for (const [k, v] of Object.entries(obj)) {
    if (v !== undefined) cleaned[k] = stripUndefined(v)
  }
  return cleaned
}

/**
 * Resolve a version string to the actual SK.
 */
async function resolveVersionSk(pk: string, version: string): Promise<string> {
  if (version === 'current') {
    const pointerCommand = new GetCommand({
      TableName: TABLE,
      Key: { pk, sk: 'program#current' },
    })
    const pointerResult = await docClient.send(pointerCommand)
    if (!pointerResult.Item) return 'program#v001'
    return (pointerResult.Item as any).ref_sk || 'program#v001'
  }
  return `program#${version}`
}

async function loadPhases(pk: string, sk: string): Promise<Phase[] | null> {
  const result = await docClient.send(new GetCommand({
    TableName: TABLE,
    Key: { pk, sk },
    ProjectionExpression: 'phases',
  }))
  if (!result.Item) return null
  return (result.Item.phases ?? []) as Phase[]
}

/**
 * Upload a video to S3 and add metadata to session
 */
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
  const sk = await resolveVersionSk(pk, version)
  const phases = await loadPhases(pk, sk)
  if (!phases) {
    throw new AppError(`Program version ${version} not found`, 404)
  }
  const session = (await listSessions(pk, sk, phases)).find(s => s.date === sessionDate)
  if (!session) {
    throw new AppError(`Session with date ${sessionDate} not found`, 404)
  }

  // Generate video ID
  const videoId = uuidv4()
  const extension = filename.split('.').pop() || 'mp4'
  const s3Key = `videos/${sessionDate}/${videoId}.${extension}`

  console.log(`[VideoController] Starting upload to S3: bucket=${S3_BUCKET}, key=${s3Key}, mime=${mimeType}`)

  try {
    // Upload to S3 with metadata for Lambda
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
          sk,
        },
      },
    })

    upload.on('httpUploadProgress', (progress) => {
      console.log(`[VideoController] Upload progress for ${videoId}: ${progress.loaded}/${progress.total}`)
    })

    await upload.done()
    console.log(`[VideoController] S3 upload successful: ${videoId}`)
  } catch (err) {
    console.error(`[VideoController] S3 upload failed for ${videoId}:`, err)
    throw new AppError(`Failed to upload video to storage: ${String(err)}`, 500)
  }

  const videoUrl = `https://${S3_BUCKET}.s3.${S3_REGION}.amazonaws.com/${s3Key}`

  const video: SessionVideo = {
    video_id: videoId,
    s3_key: s3Key,
    video_url: videoUrl,
    ...(exerciseName !== undefined && { exercise_name: exerciseName }),
    ...(setNumber !== undefined && { set_number: setNumber }),
    ...(notes !== undefined && { notes }),
    uploaded_at: new Date().toISOString(),
    thumbnail_status: 'pending',
  }

  await patchSessionByDate(pk, sk, sessionDate, {
    videos: [...(session.videos || []), video],
  } as Partial<Session>, phases)

  return video
}

/**
 * Remove a video from a session
 */
export async function removeSessionVideo(
  pk: string,
  version: string,
  sessionDate: string,
  videoId: string
): Promise<void> {
  const sk = await resolveVersionSk(pk, version)
  const phases = await loadPhases(pk, sk)
  if (!phases) {
    throw new AppError(`Program version ${version} not found`, 404)
  }
  const session = (await listSessions(pk, sk, phases)).find(s => s.date === sessionDate)
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

  // Delete from S3
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
  await patchSessionByDate(pk, sk, sessionDate, {
    videos: videos.length > 0 ? videos : undefined,
  } as Partial<Session>, phases)
}

/**
 * Update video thumbnail URL (called by Lambda)
 */
export async function updateVideoThumbnail(
  pk: string,
  version: string,
  sessionDate: string,
  videoId: string,
  thumbnailUrl: string,
  thumbnailS3Key: string,
  status: 'ready' | 'failed'
): Promise<void> {
  const sk = await resolveVersionSk(pk, version)
  const phases = await loadPhases(pk, sk)
  if (!phases) {
    throw new AppError(`Program version ${version} not found`, 404)
  }
  const session = (await listSessions(pk, sk, phases)).find(s => s.date === sessionDate)
  if (!session) {
    throw new AppError(`Session with date ${sessionDate} not found`, 404)
  }

  if (!session.videos) {
    throw new AppError(`Session has no videos`, 404)
  }

  const videos = [...session.videos]
  const videoIndex = videos.findIndex(
    v => v.video_id === videoId
  )

  if (videoIndex === -1) {
    throw new AppError(`Video ${videoId} not found`, 404)
  }

  videos[videoIndex] = {
    ...videos[videoIndex],
    thumbnail_url: thumbnailUrl,
    thumbnail_s3_key: thumbnailS3Key,
    thumbnail_status: status,
  }

  await patchSessionByDate(pk, sk, sessionDate, { videos } as Partial<Session>, phases)
}

export async function getVideoLibrary(
  pk: string,
  version: string,
  exercise?: string,
  sort: 'newest' | 'oldest' = 'newest'
): Promise<{ videos: VideoLibraryItem[]; exercises: string[] }> {
  const sk = await resolveVersionSk(pk, version)
  const phases = await loadPhases(pk, sk)
  if (!phases) {
    return { videos: [], exercises: [] }
  }

  const sessions = await listSessions(pk, sk, phases)
  const items: VideoLibraryItem[] = []
  const exerciseSet = new Set<string>()

  for (const session of sessions) {
    if (!session.videos || session.videos.length === 0) continue

    for (const video of session.videos) {
      if (exercise && video.exercise_name !== exercise) continue

      const match = video.exercise_name
        ? session.exercises.find((e) => e.name === video.exercise_name)
        : undefined

      if (video.exercise_name) exerciseSet.add(video.exercise_name)

      items.push({
        video,
        session_date: session.date,
        day: session.day,
        week_number: session.week_number,
        phase_name: session.phase?.name ?? '',
        exercise_sets: match?.sets ?? 0,
        exercise_reps: match?.reps ?? 0,
        exercise_kg: match?.kg ?? null,
      })
    }
  }

  items.sort((a, b) => {
    const cmp = a.session_date.localeCompare(b.session_date)
    return sort === 'newest' ? -cmp : cmp
  })

  return {
    videos: stripUndefined(items),
    exercises: Array.from(exerciseSet).sort(),
  }
}
