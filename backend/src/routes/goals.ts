import { Router } from 'express'
import * as goalsController from '../controllers/goalsController'

export const goalsRouter = Router()

goalsRouter.get('/', async (req, res, next) => {
  try {
    const goals = await goalsController.getGoals(req.mapped_pk!)
    res.json({ data: goals, error: null })
  } catch (err) {
    next(err)
  }
})

goalsRouter.put('/', async (req, res, next) => {
  try {
    const { goals } = req.body as { goals: unknown[] }

    if (!Array.isArray(goals)) {
      return res.status(400).json({
        data: null,
        error: 'goals must be an array',
      })
    }

    await goalsController.updateGoals(req.mapped_pk!, goals)
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})
