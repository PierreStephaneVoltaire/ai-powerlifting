import { Router } from 'express'
import * as programController from '../controllers/programController'
import { invokeLambda } from '../utils/lambda'
import type { PlannedExercise, LiftProfile } from '@powerlifting/types'

export const programsRouter = Router()

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
programsRouter.put('/:version/meta', async (req, res, next) => {
  try {
    const { field, value } = req.body

    if (!field || value === undefined) {
      return res.status(400).json({
        data: null,
        error: 'Missing field or value in request body',
      })
    }

    await programController.updateMetaField(req.mapped_pk!, req.params.version, field, value)
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})

// PUT /api/programs/:version/body-weight - Update body weight
programsRouter.put('/:version/body-weight', async (req, res, next) => {
  try {
    const { weightKg } = req.body

    if (typeof weightKg !== 'number') {
      return res.status(400).json({
        data: null,
        error: 'weightKg must be a number',
      })
    }

    await programController.updateMetaField(req.mapped_pk!, req.params.version, 'current_body_weight_kg', weightKg)
    await programController.updateMetaField(req.mapped_pk!, req.params.version, 'current_body_weight_lb', weightKg * 2.20462)
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})

// PUT /api/programs/:version/phases - Update phases
programsRouter.put('/:version/phases', async (req, res, next) => {
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

    await programController.updatePhases(req.mapped_pk!, req.params.version, phases, block)
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})

// POST /api/programs/:version/designer/batch-week - Batch create planned sessions for a week
programsRouter.post('/:version/designer/batch-week', async (req, res, next) => {
  try {
    const { week_number, week_label, days, phase_name, exercises } = req.body as {
      week_number: number
      week_label: string
      days: Array<{ date: string; day: string }>
      phase_name: string
      exercises: PlannedExercise[]
    }

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
      exercises || []
    )
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})

// PUT /api/programs/:version/lift-profiles - Update lift profiles
programsRouter.put('/:version/lift-profiles', async (req, res, next) => {
  try {
    const { liftProfiles } = req.body as { liftProfiles: LiftProfile[] }

    if (!Array.isArray(liftProfiles)) {
      return res.status(400).json({
        data: null,
        error: 'liftProfiles must be an array',
      })
    }

    await programController.updateLiftProfiles(req.mapped_pk!, req.params.version, liftProfiles)
    invokeLambda('pod_training_program', { function: 'health_invalidate_program_cache',  pk: req.mapped_pk }).catch((err) => {
      console.warn('Failed to invalidate IF health program cache after lift profile update:', err)
    })
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})

// PUT /api/programs/:version/designer/:date/:index/planned-exercises - Update planned exercises on a session
programsRouter.put('/:version/designer/:date/:index/planned-exercises', async (req, res, next) => {
  try {
    const { planned_exercises } = req.body as { planned_exercises: PlannedExercise[] }
    const index = parseInt(req.params.index, 10)

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
      planned_exercises
    )
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})

// PATCH /api/programs/:version/archive - Archive a program
programsRouter.patch('/:version/archive', async (req, res, next) => {
  try {
    await programController.archiveProgram(req.mapped_pk!, req.params.version)
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})

// PATCH /api/programs/:version/unarchive - Unarchive a program
programsRouter.patch('/:version/unarchive', async (req, res, next) => {
  try {
    await programController.unarchiveProgram(req.mapped_pk!, req.params.version)
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})
