import { Router } from 'express'
import multer from 'multer'
import * as videoController from '../controllers/videoController'

const upload = multer({
  storage: multer.memoryStorage(),
  limits: {
    fileSize: 500 * 1024 * 1024, // 500MB max
  },
  fileFilter: (_req, file, cb) => {
    const validTypes = ['video/mp4', 'video/quicktime', 'video/webm', 'video/x-msvideo']
    if (validTypes.includes(file.mimetype)) {
      cb(null, true)
    } else {
      cb(new Error('Invalid file type. Only MP4, MOV, and WebM are allowed.'))
    }
  },
})

export const videosRouter = Router({ mergeParams: true })

// GET /api/videos - List all videos across sessions
videosRouter.get('/', async (req, res, next) => {
  try {
    const version = (req.query.version as string) || 'current'
    const exercise = req.query.exercise as string | undefined
    const sort = (req.query.sort as 'newest' | 'oldest') || 'newest'

    const result = await videoController.getVideoLibrary(req.effectivePk!, version, exercise, sort)
    res.json({ data: result, error: null })
  } catch (err) {
    next(err)
  }
})

// POST /api/videos/:version/:sessionDate - Upload video to session
videosRouter.post(
  '/:version/:sessionDate',
  upload.single('video'),
  async (req, res, next) => {
    try {
      const file = req.file

      if (!file) {
        return res.status(400).json({
          data: null,
          error: 'No video file provided',
        })
      }

      const { exerciseName, setNumber, notes } = req.body

      const video = await videoController.uploadSessionVideo(
        req.effectivePk!,
        req.params.version,
        req.params.sessionDate,
        file.buffer,
        file.originalname,
        file.mimetype,
        exerciseName || undefined,
        setNumber ? parseInt(setNumber, 10) : undefined,
        notes || undefined
      )

      res.json({ data: video, error: null })
    } catch (err) {
      next(err)
    }
  }
)

// DELETE /api/videos/:version/:sessionDate/:videoId - Remove video from session
videosRouter.delete('/:version/:sessionDate/:videoId', async (req, res, next) => {
  try {
    await videoController.removeSessionVideo(
      req.effectivePk!,
      req.params.version,
      req.params.sessionDate,
      req.params.videoId
    )
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})

// PATCH /api/videos/:version/:sessionDate/:videoId/thumbnail - Update thumbnail (for Lambda)
videosRouter.patch('/:version/:sessionDate/:videoId/thumbnail', async (req, res, next) => {
  try {
    const { thumbnailUrl, thumbnailS3Key, status } = req.body

    if (!thumbnailUrl || !thumbnailS3Key || !status) {
      return res.status(400).json({
        data: null,
        error: 'Missing thumbnailUrl, thumbnailS3Key, or status in request body',
      })
    }

    await videoController.updateVideoThumbnail(
      req.effectivePk!,
      req.params.version,
      req.params.sessionDate,
      req.params.videoId,
      thumbnailUrl,
      thumbnailS3Key,
      status
    )
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})
// GET /api/videos/media/* - Proxy media from S3 with range request support
// Range support is required for video seeking in browsers.
// Express 5 / path-to-regexp v8: use {*path} for named wildcards (`:path*` is invalid in v8).
videosRouter.get('/media/{*path}', async (req, res, next) => {
  try {
    let path = (req.params as any).path
    if (Array.isArray(path)) {
      path = path.join('/')
    }

    const range = req.headers.range as string | undefined
    const { body, contentType, contentLength, contentRange, acceptRanges, statusCode } =
      await videoController.streamMedia(path, range)

    res.status(statusCode)
    res.setHeader('Content-Type', contentType)
    res.setHeader('Accept-Ranges', acceptRanges ?? 'bytes')
    res.setHeader('Cache-Control', 'private, max-age=3600')

    if (contentLength !== undefined) {
      res.setHeader('Content-Length', contentLength)
    }
    if (contentRange) {
      res.setHeader('Content-Range', contentRange)
    }

    if (body) {
      body.on('error', (err: any) => {
        console.error(`[MediaProxy] Stream error for ${path}:`, err)
        if (!res.headersSent) {
          res.status(500).end()
        }
      })
      body.pipe(res)
    } else {
      res.status(404).end()
    }
  } catch (err) {
    next(err)
  }
})

