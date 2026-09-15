import { Router } from 'express'
import * as programController from '../controllers/programController'
import { invokeLambda } from '../utils/lambda'
import { invalidateAfter } from '../utils/cacheMiddleware'
import type { PlannedExercise, LiftProfile } from '@powerlifting/types'
import { AppError } from '../middleware/errorHandler'

function mutationEnvelope(body: unknown): { expected_revision: number; idempotency_key: string; session_id?: string } {
  const input = body && typeof body === 'object' ? body as Record<string, unknown> : {}
  if (typeof input.expected_revision !== 'number' || !Number.isInteger(input.expected_revision) || input.expected_revision < 0) throw new AppError('expected_revision must be a nonnegative integer', 400)
  if (typeof input.idempotency_key !== 'string' || !input.idempotency_key.trim()) throw new AppError('idempotency_key must be a nonempty string', 400)
  const session_id = typeof input.session_id === 'string' ? input.session_id : undefined
  return { expected_revision: input.expected_revision, idempotency_key: input.idempotency_key, ...(session_id ? { session_id } : {}) }
}

export const programsRouter = Router()

programsRouter.post('/current/blocks/transition', invalidateAfter(['program:current', 'sessions:current', 'programs', 'analytics']), async (req, res, next) => {
  try {
    const result = await invokeLambda('block_transition', req.body)
    res.json({ data: result, error: null })
  } catch (error) { next(error) }
})

// GET /api/programs - List all program versions
programsRouter.get('/', async (req, res, next) => {
  try {
    const programs = await programController.listPrograms(req.mapped_pk!)
    res.json({ data: programs, error: null })
  } catch (err) {
    next(err)
  }
})

// GET /api/programs/:version - Get a specific program
programsRouter.get('/:version', async (req, res, next) => {
  try {
    const program = await programController.getProgram(req.mapped_pk!, req.params.version)
    res.json({ data: program, error: null })
  } catch (err) {
    next(err)
  }
})

// PUT /api/programs/:version/meta - Update a meta field
programsRouter.put('/:version/meta', invalidateAfter((req) => [`program:${req.params.version}`]), async (req, res, next) => {
  try {
    const { field, value, updates } = req.body
    const envelope = mutationEnvelope(req.body)

    if ((!field || value === undefined) && (!updates || typeof updates !== 'object' || Array.isArray(updates))) {
      return res.status(400).json({
        data: null,
        error: 'Missing field or value in request body',
      })
    }

    const result = updates
      ? await programController.updateMetaFields(req.mapped_pk!, req.params.version, updates, envelope)
      : await programController.updateMetaField(req.mapped_pk!, req.params.version, field, value, envelope)
    res.json({ data: result, error: null })
  } catch (err) {
    next(err)
  }
})

// PUT /api/programs/:version/body-weight - Update body weight
programsRouter.put('/:version/body-weight', invalidateAfter((req) => [`program:${req.params.version}`, `weight-log:${req.params.version}`]), async (req, res, next) => {
  try {
    const { weightKg } = req.body
    const envelope = mutationEnvelope(req.body)

    if (typeof weightKg !== 'number') {
      return res.status(400).json({
        data: null,
        error: 'weightKg must be a number',
      })
    }

    const result = await programController.updateBodyWeight(req.mapped_pk!, req.params.version, weightKg, envelope)
    res.json({ data: result, error: null })
  } catch (err) {
    next(err)
  }
})

// PUT /api/programs/:version/phases - Update phases
programsRouter.put('/:version/phases', invalidateAfter((req) => [`program:${req.params.version}`]), async (req, res, next) => {
  try {
    const { phases, block } = req.body
    const envelope = mutationEnvelope(req.body)

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

    const result = await programController.updatePhases(req.mapped_pk!, req.params.version, phases, block, envelope)
    res.json({ data: result, error: null })
  } catch (err) {
    next(err)
  }
})

// POST /api/programs/:version/designer/batch-week - Batch create planned sessions for a week
programsRouter.post('/:version/designer/batch-week', invalidateAfter((req) => [`program:${req.params.version}`, `sessions:${req.params.version}`]), async (req, res, next) => {
  try {
    const { week_number, week_label, days, phase_name, exercises } = req.body as {
      week_number: number
      week_label: string
      days: Array<{ date: string; day: string }>
      phase_name: string
      exercises: PlannedExercise[]
    }
    const envelope = mutationEnvelope(req.body)

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
      req.params.version,
      week_number,
      week_label,
      days,
      phase_name || 'Unknown',
      exercises || [],
      envelope
    )
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})

// PUT /api/programs/:version/lift-profiles - Update lift profiles
programsRouter.put('/:version/lift-profiles', invalidateAfter((req) => [`program:${req.params.version}`]), async (req, res, next) => {
  try {
    const { liftProfiles } = req.body as { liftProfiles: LiftProfile[] }
    const envelope = mutationEnvelope(req.body)

    if (!Array.isArray(liftProfiles)) {
      return res.status(400).json({
        data: null,
        error: 'liftProfiles must be an array',
      })
    }

    const result = await programController.updateLiftProfiles(req.mapped_pk!, req.params.version, liftProfiles, envelope)
    invokeLambda('pod_training_program', { function: 'health_invalidate_program_cache',  pk: req.mapped_pk }).catch((err) => {
      console.warn('Failed to invalidate IF health program cache after lift profile update:', err)
    })
    res.json({ data: result, error: null })
  } catch (err) {
    next(err)
  }
})

// PUT /api/programs/:version/designer/:date/:index/planned-exercises - Update planned exercises on a session
programsRouter.put('/:version/designer/:date/:index/planned-exercises', invalidateAfter((req) => [`program:${req.params.version}`, `sessions:${req.params.version}`]), async (req, res, next) => {
  try {
    const { planned_exercises } = req.body as { planned_exercises: PlannedExercise[] }
    const index = parseInt(req.params.index, 10)
    const envelope = mutationEnvelope(req.body)

    if (!Array.isArray(planned_exercises)) {
      return res.status(400).json({
        data: null,
        error: 'planned_exercises must be an array',
      })
    }

    await programController.updatePlannedExercises(
      req.mapped_pk!,
      req.params.version,
      req.params.date,
      index,
      planned_exercises,
      envelope
    )
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})

// PATCH /api/programs/:version/archive - Archive a program
programsRouter.patch('/:version/archive', invalidateAfter((req) => [`program:${req.params.version}`, 'programs']), async (req, res, next) => {
  try {
    const result = await programController.archiveProgram(req.mapped_pk!, req.params.version, mutationEnvelope(req.body))
    res.json({ data: result, error: null })
  } catch (err) {
    next(err)
  }
})

// PATCH /api/programs/:version/unarchive - Unarchive a program
programsRouter.patch('/:version/unarchive', invalidateAfter((req) => [`program:${req.params.version}`, 'programs']), async (req, res, next) => {
  try {
    const result = await programController.unarchiveProgram(req.mapped_pk!, req.params.version, mutationEnvelope(req.body))
    res.json({ data: result, error: null })
  } catch (err) {
    next(err)
  }
})
