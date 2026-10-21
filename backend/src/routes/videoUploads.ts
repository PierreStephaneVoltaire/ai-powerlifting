import { Router } from 'express'
import type { Request } from 'express'
import * as uploads from '../controllers/videoUploadController'
import { isUploadKeyFor, MAX_VIDEO_BYTES, normalizeParts, parsePartNumber, VIDEO_PART_BYTES } from '../utils/videoMultipart'
import type { LiftProfileVideoAngle } from '@powerlifting/types'

export const videoUploadsRouter = Router({ mergeParams: true })
export const videoMimeTypes = ['video/mp4', 'video/quicktime', 'video/webm', 'video/x-msvideo']

type Params = { version: string; sessionDate: string; videoId?: string; partNumber?: string }

interface UploadBody {
  filename?: string
  mimeType?: string
  size?: number
  uploadId?: string
  s3Key?: string
  parts?: unknown
  exerciseName?: string
  setNumber?: number
  notes?: string
  idempotencyKey?: string
  sessionId?: string
  lift?: 'squat' | 'bench' | 'deadlift'
  angle?: LiftProfileVideoAngle
  targetRevision?: number
}

function uploadTarget(req: Request<Params>, body: UploadBody): uploads.VideoUploadTarget {
  return {
    sessionId: body.sessionId || req.get('X-Session-Id') || undefined,
    lift: body.lift || undefined,
    angle: body.angle || undefined,
    targetRevision: typeof body.targetRevision === 'number' ? body.targetRevision : undefined,
    idempotencyKey: body.idempotencyKey || req.get('Idempotency-Key') || undefined,
  }
}

function uploadRef(req: Request<Params>, source: { uploadId?: unknown; s3Key?: unknown }): { uploadId: string; s3Key: string } | null {
  const { uploadId, s3Key } = source
  if (typeof uploadId !== 'string' || !uploadId || typeof s3Key !== 'string') return null
  return isUploadKeyFor(s3Key, req.params.sessionDate, req.params.videoId || '') ? { uploadId, s3Key } : null
}

videoUploadsRouter.post('/', async (req: Request<Params>, res, next) => {
  try {
    const body = (req.body || {}) as UploadBody
    if (!body.filename || !body.mimeType || !videoMimeTypes.includes(body.mimeType)) {
      return res.status(400).json({ data: null, error: 'A supported video filename and MIME type are required' })
    }
    if (typeof body.size !== 'number' || !Number.isInteger(body.size) || body.size <= 0 || body.size > MAX_VIDEO_BYTES) {
      return res.status(413).json({ data: null, error: 'Video size must be between 1 byte and 500 MB' })
    }
    const session = await uploads.startVideoUpload(
      req.mapped_pk!, req.params.version, req.params.sessionDate, body.filename, body.mimeType, body.size, uploadTarget(req, body),
    )
    res.json({ data: session, error: null })
  } catch (err) {
    next(err)
  }
})

videoUploadsRouter.put('/:videoId/parts/:partNumber', async (req: Request<Params>, res, next) => {
  try {
    const ref = uploadRef(req, req.query)
    const partNumber = parsePartNumber(req.params.partNumber)
    if (!ref || partNumber === null) return res.status(400).json({ data: null, error: 'Invalid upload part reference' })
    const contentLength = Number(req.get('Content-Length'))
    if (!Number.isInteger(contentLength) || contentLength <= 0) return res.status(411).json({ data: null, error: 'Content-Length is required' })
    if (contentLength > VIDEO_PART_BYTES) return res.status(413).json({ data: null, error: 'Upload part is too large' })
    const etag = await uploads.uploadVideoPart(ref.s3Key, ref.uploadId, partNumber, req, contentLength)
    res.json({ data: { partNumber, etag }, error: null })
  } catch (err) {
    next(err)
  }
})

videoUploadsRouter.post('/:videoId/complete', async (req: Request<Params>, res, next) => {
  try {
    const body = (req.body || {}) as UploadBody
    const ref = uploadRef(req, body)
    const parts = normalizeParts(body.parts)
    if (!ref || !parts) return res.status(400).json({ data: null, error: 'Invalid upload completion request' })
    const video = await uploads.completeVideoUpload(
      req.mapped_pk!, req.params.version, req.params.sessionDate, req.params.videoId!, ref.s3Key, ref.uploadId, parts,
      {
        exerciseName: body.exerciseName || undefined,
        setNumber: typeof body.setNumber === 'number' ? body.setNumber : undefined,
        notes: body.notes || undefined,
      },
      uploadTarget(req, body),
    )
    res.json({ data: video, error: null })
  } catch (err) {
    next(err)
  }
})

videoUploadsRouter.delete('/:videoId', async (req: Request<Params>, res, next) => {
  try {
    const ref = uploadRef(req, req.query)
    if (!ref) return res.status(400).json({ data: null, error: 'Invalid upload reference' })
    await uploads.abortVideoUpload(ref.s3Key, ref.uploadId)
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})
