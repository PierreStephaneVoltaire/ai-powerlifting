import { v4 as uuidv4 } from 'uuid'
import { GetCommand } from '@aws-sdk/lib-dynamodb'
import { S3Client, DeleteObjectCommand, GetObjectCommand } from '@aws-sdk/client-s3'
import { Upload } from '@aws-sdk/lib-storage'
import { docClient, TABLE } from '../db/dynamo'
import { AppError } from '../middleware/errorHandler'
import { listSessions, patchSessionByDate, transformVideo, getProxyUrl } from '../services/sessionStore'
import { sortVideos } from '../utils/videoSort'
import type { Exercise, Phase, Session, SessionVideo, VideoLibraryItem, VideoSort } from '@powerlifting/types'

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

export interface StreamMediaResult {
  body: any
  contentType: string
  contentLength?: number
  contentRange?: string
  acceptRanges?: string
  statusCode: number
}

export async function streamMedia(key: string, range?: string): Promise<StreamMediaResult> {
  try {
    const command = new GetObjectCommand({
      Bucket: S3_BUCKET,
      Key: key,
      ...(range ? { Range: range } : {}),
    })
    const response = await s3Client.send(command)
    return {
      body: response.Body,
      contentType: response.ContentType || 'application/octet-stream',
      contentLength: response.ContentLength,
      contentRange: response.ContentRange,
      acceptRanges: response.AcceptRanges ?? 'bytes',
      statusCode: range && response.ContentRange ? 206 : 200,
    }
  } catch (err: any) {
    if (err?.name === 'NoSuchKey' || err?.$metadata?.httpStatusCode === 404) {
      throw new AppError('Media not found', 404)
    }
    console.error(`[VideoController] Failed to fetch media from S3: ${key}`, err)
    throw new AppError('Media not found', 404)
  }
}

function stripUndefined(obj: any): any {
  if (obj === null || typeof obj !== 'object') return obj
  if (Array.isArray(obj)) return obj.map(stripUndefined)
  const cleaned: any = {}
  for (const [k, v] of Object.entries(obj)) {
    if (v !== undefined) cleaned[k] = stripUndefined(v)
  }
  return cleaned
}

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

  const video: SessionVideo = {
    video_id: videoId,
    s3_key: s3Key,
    video_url: getProxyUrl(s3Key),
    ...(exerciseName !== undefined && { exercise_name: exerciseName }),
    ...(setNumber !== undefined && { set_number: setNumber }),
    ...(notes !== undefined && { notes }),
    uploaded_at: new Date().toISOString(),
    thumbnail_status: 'pending',
  }

  await patchSessionByDate(pk, sk, sessionDate, {
    videos: [...(session.videos || []), video],
  } as Partial<Session>, phases)

  return transformVideo(video)
}

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
    thumbnail_url: getProxyUrl(thumbnailS3Key),
    thumbnail_s3_key: thumbnailS3Key,
    thumbnail_status: status,
  }

  await patchSessionByDate(pk, sk, sessionDate, { videos } as Partial<Session>, phases)
}

export async function getVideoLibrary(
  pk: string,
  version: string,
  exercise?: string,
  sort: VideoSort = 'newest'
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

      // A session can have multiple exercise entries with the same name.
      // Straight sets of the same weight are grouped into a single entry
      // with `sets: N`; a new weight produces a new entry that starts at
      // `sets: 1`. The video's stored `set_number` is the CUMULATIVE set
      // number across the same-named block, so 3×175 + 1×455 produces two
      // Squat entries whose sets occupy [1..3] and [4..4] respectively, and
      // a video for the 455 single is tagged `set_number: 4`.
      //
      // Walk the same-named block in order, tracking the running set
      // offset, and pick the entry whose [start, start + sets - 1] range
      // contains the video's set_number. Same-named exercises are stored
      // consecutively in `session.exercises` (the volume/singles-phase
      // convention), so the ranges don't overlap. Falls back to the first
      // match when set_number is missing or out of range, preserving the
      // old behavior for legacy/edge-case data.
      let match: Exercise | undefined
      if (video.exercise_name) {
        const sameName = session.exercises.filter((e) => e.name === video.exercise_name)
        const setNumber = typeof video.set_number === 'number' ? video.set_number : null
        if (setNumber !== null && sameName.length > 0) {
          let cumulativeSets = 0
          for (const candidate of sameName) {
            const setCount = Math.max(0, Math.round(Number(candidate.sets) || 0))
            const start = cumulativeSets + 1
            const end = cumulativeSets + setCount
            if (setNumber >= start && setNumber <= end) {
              match = candidate
              break
            }
            cumulativeSets = end
          }
        }
        if (!match) {
          match = sameName[0]
        }
      }

      if (video.exercise_name) exerciseSet.add(video.exercise_name)

      items.push({
        video: transformVideo(video),
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

  return {
    videos: stripUndefined(sortVideos(items, sort)),
    exercises: Array.from(exerciseSet).sort(),
  }
}
