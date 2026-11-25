import { Router } from 'express'
import * as weightController from '../controllers/weightController'
import { cacheGet, invalidateAfter } from '../utils/cacheMiddleware'
import type { WeightEntry } from '@powerlifting/types'

export const weightRouter = Router()

// GET /api/weight/current - Get weight log
weightRouter.get('/current', cacheGet((req) => [`weight-log:current`]), async (req, res, next) => {
  try {
    const log = await weightController.getWeightLog(req.mapped_pk!)
    res.json({ data: log, error: null })
  } catch (err) {
    next(err)
  }
})

// POST /api/weight/current - Add weight entry
weightRouter.post('/current', invalidateAfter((req) => [`weight-log:current`]), async (req, res, next) => {
  try {
    const { date, kg } = req.body

    if (!date || typeof kg !== 'number') {
      return res.status(400).json({
        data: null,
        error: 'Missing date or kg in request body',
      })
    }

    const entry: WeightEntry = { date, kg }
    await weightController.addWeightEntry(req.mapped_pk!, entry)
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})

// DELETE /api/weight/current/:date - Remove weight entry
weightRouter.delete('/current/:date', invalidateAfter((req) => [`weight-log:current`]), async (req, res, next) => {
  try {
    await weightController.removeWeightEntry(req.mapped_pk!, req.params.date)
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})
