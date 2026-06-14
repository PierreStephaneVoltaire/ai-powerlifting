import { Router } from 'express'
import * as maxController from '../controllers/maxController'
import type { MaxEntry } from '@powerlifting/types'

export const maxesRouter = Router()

// GET /api/maxes/:version - Get current targets and history
maxesRouter.get('/:version', async (req, res, next) => {
  try {
    const [targets, history] = await Promise.all([
      maxController.getTargetMaxes(req.mapped_pk!, req.params.version),
      maxController.getMaxHistory(req.mapped_pk!, req.params.version),
    ])
    res.json({
      data: { targets, history },
      error: null,
    })
  } catch (err) {
    next(err)
  }
})

// PUT /api/maxes/:version - Update target maxes
maxesRouter.put('/:version', async (req, res, next) => {
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

    await maxController.updateTargetMaxes(req.mapped_pk!, req.params.version, {
      squat_kg,
      bench_kg,
      deadlift_kg,
    })
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})

// POST /api/maxes/:version/history - Add to max history
maxesRouter.post('/:version/history', async (req, res, next) => {
  try {
    const entry = req.body as MaxEntry

    if (!entry.date) {
      return res.status(400).json({
        data: null,
        error: 'Missing date in max entry',
      })
    }

    await maxController.addMaxEntry(req.mapped_pk!, req.params.version, entry)
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})
