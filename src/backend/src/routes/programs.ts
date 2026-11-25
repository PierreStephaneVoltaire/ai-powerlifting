import type { SessionTarget } from '../controllers/sessionController'
import { Router } from 'express'
import * as programController from '../controllers/programController'
import { callOperation } from '../utils/operations'
import { invalidateAfter } from '../utils/cacheMiddleware'
import type { PlannedExercise, LiftProfile } from '@powerlifting/types'

function sessionTarget(body: unknown): SessionTarget {
  const input = body && typeof body === 'object' ? body as Record<string, unknown> : {}
  return typeof input.session_id === 'string' ? { session_id: input.session_id } : {}
}

export const programsRouter = Router()

programsRouter.post('/current/blocks/transition', invalidateAfter(['program:current', 'sessions:current', 'programs', 'analytics']), async (req, res, next) => {
  try {
    const result = await callOperation('block_transition', req.body)
    res.json({ data: result, error: null })
  } catch (error) { next(error) }
})

// GET /api/programs/current - Get a specific program
programsRouter.get('/current', async (req, res, next) => {
  try {
    const program = await programController.getProgram(req.mapped_pk!)
    res.json({ data: program, error: null })
  } catch (err) {
    next(err)
  }
})

// PUT /api/programs/current/meta - Update a meta field
programsRouter.put('/current/meta', invalidateAfter((req) => [`program:current`]), async (req, res, next) => {
  try {
    const { field, value, updates } = req.body

    if ((!field || value === undefined) && (!updates || typeof updates !== 'object' || Array.isArray(updates))) {
      return res.status(400).json({
        data: null,
        error: 'Missing field or value in request body',
      })
    }

    const result = updates
      ? await programController.updateMetaFields(req.mapped_pk!, updates)
      : await programController.updateMetaField(req.mapped_pk!, field, value)
    res.json({ data: result, error: null })
  } catch (err) {
    next(err)
  }
})

// PUT /api/programs/current/body-weight - Update body weight
programsRouter.put('/current/body-weight', invalidateAfter((req) => [`program:current`, `weight-log:current`]), async (req, res, next) => {
  try {
    const { weightKg } = req.body

    if (typeof weightKg !== 'number') {
      return res.status(400).json({
        data: null,
        error: 'weightKg must be a number',
      })
    }

    const result = await programController.updateBodyWeight(req.mapped_pk!, weightKg)
    res.json({ data: result, error: null })
  } catch (err) {
    next(err)
  }
})

// PUT /api/programs/current/phases - Update phases
programsRouter.put('/current/phases', invalidateAfter((req) => [`program:current`]), async (req, res, next) => {
  try {
    const { phases, block } = req.body

    if (!Array.isArray(phases)) {
      return res.status(400).json({
        data: null,
        error: 'phases must be an array',
      })
    }

    if (block !== undefined && typeof block !== 'string') {
      return res.status(400).json({
        data: null,
        error: 'block must be a string when provided',
      })
    }

    const result = await programController.updatePhases(req.mapped_pk!, phases, block)
    res.json({ data: result, error: null })
  } catch (err) {
    next(err)
  }
})

// POST /api/programs/current/designer/batch-week - Batch create planned sessions for a week
programsRouter.post('/current/designer/batch-week', invalidateAfter((req) => [`program:current`, `sessions:current`]), async (req, res, next) => {
  try {
    const { week_number, week_label, days, phase_name, exercises } = req.body as {
      week_number: number
      week_label: string
      days: Array<{ date: string; day: string }>
      phase_name: string
      exercises: PlannedExercise[]
    }
    const target = sessionTarget(req.body)

    if (!week_number || !week_label || !Array.isArray(days) || days.length === 0) {
      return res.status(400).json({
        data: null,
        error: 'Missing required fields: week_number, week_label, days',
      })
    }

    for (const day of days) {
      if (!day.date || !day.day) {
        return res.status(400).json({
          data: null,
          error: 'Each day must have date and day fields',
        })
      }
    }

    await programController.batchCreateWeek(
      req.mapped_pk!,
      week_number,
      week_label,
      days,
      phase_name || 'Unknown',
      exercises || [],
      target
    )
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})

// PUT /api/programs/current/lift-profiles - Update lift profiles
programsRouter.put('/current/lift-profiles', invalidateAfter((req) => [`program:current`]), async (req, res, next) => {
  try {
    const { liftProfiles } = req.body as { liftProfiles: LiftProfile[] }

    if (!Array.isArray(liftProfiles)) {
      return res.status(400).json({
        data: null,
        error: 'liftProfiles must be an array',
      })
    }

    const result = await programController.updateLiftProfiles(req.mapped_pk!, liftProfiles)
    callOperation('health_invalidate_program_cache', { pk: req.mapped_pk }).catch((err) => {
      console.warn('Failed to invalidate IF health program cache after lift profile update:', err)
    })
    res.json({ data: result, error: null })
  } catch (err) {
    next(err)
  }
})

// PUT /api/programs/current/designer/:date/:index/planned-exercises - Update planned exercises on a session
programsRouter.put('/current/designer/:date/:index/planned-exercises', invalidateAfter((req) => [`program:current`, `sessions:current`]), async (req, res, next) => {
  try {
    const { planned_exercises } = req.body as { planned_exercises: PlannedExercise[] }
    const index = parseInt(req.params.index, 10)
    const target = sessionTarget(req.body)

    if (!Array.isArray(planned_exercises)) {
      return res.status(400).json({
        data: null,
        error: 'planned_exercises must be an array',
      })
    }

    await programController.updatePlannedExercises(
      req.mapped_pk!,
      req.params.date,
      index,
      planned_exercises,
      target
    )
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})
