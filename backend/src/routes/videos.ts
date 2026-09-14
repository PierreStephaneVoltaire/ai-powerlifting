import { Router } from 'express'
import multer from 'multer'
import { unlink } from 'fs/promises'
import type { NextFunction, Request, Response } from 'express'
import * as videoController from '../controllers/videoController'
import { isVideoSort } from '../utils/videoSort'
import type { VideoSort } from '@powerlifting/types'

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
      const video = await videoController.uploadSessionVideo(
        req.mapped_pk!, req.params.version, req.params.sessionDate, req.file.path, req.file.originalname,
        req.file.mimetype, req.body.exerciseName || undefined,
        req.body.setNumber ? Number(req.body.setNumber) : undefined, req.body.notes || undefined,
      )
      return res.json({ data: video, error: null })
    } catch (err) {
      return next(err)
    } finally {
      await unlink(req.file.path).catch(() => undefined)
    }
  }
  try {
    const { filename, mimetype } = (req.body || {}) as { filename?: string; mimetype?: string }
    if (!filename || !mimetype) {
      return res.status(400).json({ data: null, error: 'filename and mimetype are required' })
    }
    if (!videoMimeTypes.includes(mimetype)) {
      return res.status(400).json({ data: null, error: 'Invalid video MIME type' })
    }
    const result = await videoController.presignSessionVideo(
      req.mapped_pk!,
      req.params.version,
      req.params.sessionDate,
      filename,
      mimetype,
    )
    res.json({ data: result, error: null })
  } catch (err) {
    next(err)
  }
})

async function serveMedia(req: import('express').Request, res: import('express').Response, next: import('express').NextFunction) {
  try {
    const key = req.params[0]
    if (!key || key.includes('..')) return res.status(400).end()
    const head = await videoController.headMedia(key)
    const range = typeof req.headers.range === 'string' ? req.headers.range : undefined
    const object = req.method === 'HEAD' ? null : await videoController.getMedia(key, range)
    res.status(range && object ? 206 : 200)
    if (head.ContentType) res.type(head.ContentType)
    if (head.ContentLength !== undefined && !range) res.setHeader('Content-Length', String(head.ContentLength))
    if (head.ETag) res.setHeader('ETag', head.ETag)
    if (head.LastModified) res.setHeader('Last-Modified', head.LastModified.toUTCString())
    if (object?.ContentRange) res.setHeader('Content-Range', object.ContentRange)
    if (object?.ContentLength !== undefined) res.setHeader('Content-Length', String(object.ContentLength))
    if (object?.Body && req.method !== 'HEAD') {
      for await (const chunk of object.Body as AsyncIterable<Uint8Array>) res.write(chunk)
    }
    res.end()
  } catch (err) {
    next(err)
  }
}

videosRouter.get(/^\/media\/(.+)$/, serveMedia)
videosRouter.head(/^\/media\/(.+)$/, serveMedia)

videosRouter.post('/:version/:sessionDate/confirm', async (req, res, next) => {
  try {
    const { videoId, s3Key, exerciseName, setNumber, notes } = (req.body || {}) as {
      videoId?: string
      s3Key?: string
      exerciseName?: string
      setNumber?: number
      notes?: string
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
    )
    res.json({ data: video, error: null })
  } catch (err) {
    next(err)
  }
})

videosRouter.patch('/:version/:sessionDate/:videoId/thumbnail', async (req, res, next) => {
  try {
    const { thumbnailUrl, thumbnailS3Key, status } = req.body || {}
    if (!thumbnailUrl || !thumbnailS3Key || !status) {
      return res.status(400).json({
        data: null,
        error: 'Missing thumbnailUrl, thumbnailS3Key, or status in request body',
      })
    }
    await videoController.updateVideoThumbnail(
      req.mapped_pk!,
      req.params.version,
      req.params.sessionDate,
      req.params.videoId,
      thumbnailUrl,
      thumbnailS3Key,
      status,
    )
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})
