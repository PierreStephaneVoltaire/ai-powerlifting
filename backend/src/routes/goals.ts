import { Router } from 'express'
import * as goalsController from '../controllers/goalsController'
import type { AthleteGoal } from '@powerlifting/types'

export const goalsRouter = Router({ mergeParams: true })

goalsRouter.get('/:version', async (req, res, next) => {
  try {
    const goals = await goalsController.getGoals(req.mapped_pk!, req.params.version)
    res.json({ data: goals, error: null })
  } catch (err) {
    next(err)
  }
})

goalsRouter.put('/:version', async (req, res, next) => {
  try {
    const { goals } = req.body as { goals: AthleteGoal[] }

    if (!Array.isArray(goals)) {
      return res.status(400).json({
        data: null,
        error: 'goals must be an array',
      })
    }

    await goalsController.updateGoals(req.mapped_pk!, req.params.version, goals)
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})
