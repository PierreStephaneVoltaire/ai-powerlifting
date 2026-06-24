import { Router } from 'express'
import multer from 'multer'
import * as videoController from '../controllers/videoController'
import { isVideoSort } from '../utils/videoSort'
import type { VideoSort } from '@powerlifting/types'

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
    const sort: VideoSort = isVideoSort(req.query.sort) ? req.query.sort : 'newest'

    const result = await videoController.getVideoLibrary(req.mapped_pk!, version, exercise, sort)
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
        req.mapped_pk!,
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
      req.mapped_pk!,
      req.params.version,
      req.params.sessionDate,
      req.params.videoId
    )
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})

// PATCH /api/videos/:version/:sessionDate/:videoId - Update video metadata (exercise, set number, notes)
videosRouter.patch('/:version/:sessionDate/:videoId', async (req, res, next) => {
  try {
    const { exerciseName, setNumber, notes } = req.body as {
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
      }
    )
    res.json({ data: video, error: null })
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
      req.mapped_pk!,
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

