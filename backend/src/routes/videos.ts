import { Router } from 'express'
import multer from 'multer'
import { unlink } from 'fs/promises'
import type { NextFunction, Request, Response } from 'express'
import * as videoController from '../controllers/videoController'
import { isVideoSort } from '../utils/videoSort'
import { serveStoredMedia } from '../utils/serveMedia'
import { isPublicMediaKey, mediaCdnConfig, publicMediaUrl, signedMediaUrl } from '../utils/mediaCdn'
import type { LiftProfileVideoAngle, VideoSort } from '@powerlifting/types'

export const videosRouter = Router({ mergeParams: true })
const maxVideoBytes = 500 * 1024 * 1024
const videoMimeTypes = ['video/mp4', 'video/quicktime', 'video/webm', 'video/x-msvideo']
const upload = multer({
  dest: process.env.TMPDIR || '/tmp',
  limits: { fileSize: maxVideoBytes, files: 1 },
  fileFilter: (_req, file, callback) => callback(null, videoMimeTypes.includes(file.mimetype)),
})

function receiveVideo(req: Request, res: Response, next: NextFunction) {
  upload.fields([{ name: 'file', maxCount: 1 }, { name: 'video', maxCount: 1 }])(req, res, (err) => {
    if (err) return res.status(err.code === 'LIMIT_FILE_SIZE' ? 413 : 400).json({ data: null, error: err.message })
    const files = req.files as { file?: Express.Multer.File[]; video?: Express.Multer.File[] } | undefined
    req.file = files?.file?.[0] || files?.video?.[0]
    next()
  })
}

videosRouter.get('/', async (req, res, next) => {
  try {
    const version = (req.query.version as string) || 'current'
    const exercise = req.query.exercise as string | undefined
    const sort: VideoSort = isVideoSort(req.query.sort) ? req.query.sort : 'newest'
    const result = await videoController.getVideoLibrary(req.mapped_pk!, version, exercise, sort)
    res.json({ data: result, error: null })
  } catch (err) {
    next(err)
  }
})

videosRouter.post('/:version/:sessionDate', receiveVideo, async (req, res, next) => {
  if (req.file) {
    try {
      if (!videoMimeTypes.includes(req.file.mimetype)) return res.status(400).json({ data: null, error: 'Invalid video MIME type' })
      const sessionId = req.body.sessionId || req.get('X-Session-Id') || undefined
      const video = await videoController.uploadSessionVideo(
        req.mapped_pk!, req.params.version, req.params.sessionDate, req.file.path, req.file.originalname,
        req.file.mimetype, req.body.exerciseName || undefined,
        req.body.setNumber ? Number(req.body.setNumber) : undefined, req.body.notes || undefined,
      req.get('Idempotency-Key') || req.body.idempotencyKey || undefined,
        sessionId,
        req.body.lift || undefined,
        req.body.angle as LiftProfileVideoAngle | undefined,
        req.body.targetRevision ? Number(req.body.targetRevision) : undefined,
      )
      return res.json({ data: video, error: null })
    } catch (err) {
      return next(err)
    } finally {
      await unlink(req.file.path).catch(() => undefined)
    }
  }
  res.status(400).json({ data: null, error: 'file is required' })
})

async function serveMedia(req: import('express').Request, res: import('express').Response, next: import('express').NextFunction) {
  try {
    const key = req.params[0]
    if (!key || key.includes('..')) return res.status(400).end()
    const cdn = mediaCdnConfig()
    if (cdn && isPublicMediaKey(key)) {
      res.setHeader('Cache-Control', 'public, max-age=86400')
      return res.redirect(302, publicMediaUrl(cdn, key))
    }
    const resolved = await videoController.resolveMedia(req.mapped_pk!, key)
    if (cdn) {
      res.setHeader('Cache-Control', 'private, max-age=3600')
      return res.redirect(302, signedMediaUrl(cdn, resolved))
    }
    await serveStoredMedia(req, res, process.env.VIDEOS_BUCKET || 'powerlifting-session-videos', resolved)
  } catch (err) {
    next(err)
  }
}

videosRouter.get(/^\/media\/(.+)$/, serveMedia)
videosRouter.head(/^\/media\/(.+)$/, serveMedia)

videosRouter.post('/:version/:sessionDate/confirm', async (req, res, next) => {
  try {
      const { videoId, s3Key, exerciseName, setNumber, notes, expectedSize, idempotencyKey, sessionId, lift, angle, targetRevision } = (req.body || {}) as {
      videoId?: string
      s3Key?: string
      exerciseName?: string
      setNumber?: number
      notes?: string
      expectedSize?: number
      idempotencyKey?: string
      sessionId?: string
      lift?: 'squat' | 'bench' | 'deadlift'
      angle?: LiftProfileVideoAngle
      targetRevision?: number
    }
    if (!videoId || !s3Key) {
      return res.status(400).json({ data: null, error: 'videoId and s3Key are required' })
    }
    const video = await videoController.confirmSessionVideo(
      req.mapped_pk!,
      req.params.version,
      req.params.sessionDate,
      videoId,
      s3Key,
      exerciseName || undefined,
      typeof setNumber === 'number' ? setNumber : undefined,
      notes || undefined,
      typeof expectedSize === 'number' ? expectedSize : undefined,
      idempotencyKey || req.get('Idempotency-Key') || undefined,
      sessionId || req.get('X-Session-Id') || undefined,
      lift,
      angle,
      typeof targetRevision === 'number' ? targetRevision : undefined,
    )
    res.json({ data: video, error: null })
  } catch (err) {
    next(err)
  }
})

videosRouter.delete('/:version/:sessionDate/:videoId', async (req, res, next) => {
  try {
    await videoController.removeSessionVideo(
      req.mapped_pk!,
      req.params.version,
      req.params.sessionDate,
      req.params.videoId,
      ((req.body || {}) as { sessionId?: string }).sessionId || req.get('X-Session-Id') || undefined,
    )
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})

videosRouter.patch('/:version/:sessionDate/:videoId', async (req, res, next) => {
  try {
    const { exerciseName, setNumber, notes } = (req.body || {}) as {
      exerciseName?: string
      setNumber?: number
      notes?: string
    }
    const video = await videoController.updateSessionVideoMetadata(
      req.mapped_pk!,
      req.params.version,
      req.params.sessionDate,
      req.params.videoId,
      {
        exerciseName,
        setNumber: typeof setNumber === 'number' ? setNumber : undefined,
        notes,
      },
      ((req.body || {}) as { sessionId?: string }).sessionId || req.get('X-Session-Id') || undefined,
    )
    res.json({ data: video, error: null })
  } catch (err) {
    next(err)
  }
})
