import { Router } from 'express'
import * as maxController from '../controllers/maxController'
import { cacheGet, invalidateAfter } from '../utils/cacheMiddleware'
import type { MaxEntry } from '@powerlifting/types'

export const maxesRouter = Router()

// GET /api/maxes/current - Get current targets and history
maxesRouter.get('/current', cacheGet((req) => [`maxes:current`]), async (req, res, next) => {
  try {
    const [targets, history] = await Promise.all([
      maxController.getTargetMaxes(req.mapped_pk!),
      maxController.getMaxHistory(req.mapped_pk!),
    ])
    res.json({
      data: { targets, history },
      error: null,
    })
  } catch (err) {
    next(err)
  }
})

// PUT /api/maxes/current - Update target maxes
maxesRouter.put('/current', invalidateAfter((req) => [`maxes:current`, `program:current`]), async (req, res, next) => {
  try {
    const { squat_kg, bench_kg, deadlift_kg } = req.body

    if (
      typeof squat_kg !== 'number' ||
      typeof bench_kg !== 'number' ||
      typeof deadlift_kg !== 'number'
    ) {
      return res.status(400).json({
        data: null,
        error: 'Missing or invalid max values (squat_kg, bench_kg, deadlift_kg required)',
      })
    }

    const result = await maxController.updateTargetMaxes(req.mapped_pk!, {
      squat_kg,
      bench_kg,
      deadlift_kg,
    })
    res.json({ data: result, error: null })
  } catch (err) {
    next(err)
  }
})

// POST /api/maxes/current/history - Add to max history
maxesRouter.post('/current/history', invalidateAfter((req) => [`maxes:current`]), async (req, res, next) => {
  try {
    const entry = req.body

    if (!entry.date) {
      return res.status(400).json({
        data: null,
        error: 'Missing date in max entry',
      })
    }

    const history = await maxController.addMaxEntry(req.mapped_pk!, entry as MaxEntry)
    res.json({ data: history, error: null })
  } catch (err) {
    next(err)
  }
})
