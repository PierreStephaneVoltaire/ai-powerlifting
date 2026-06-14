import { Router } from 'express'
import * as weightController from '../controllers/weightController'
import type { WeightEntry } from '@powerlifting/types'

export const weightRouter = Router()

// GET /api/weight/:version - Get weight log
weightRouter.get('/:version', async (req, res, next) => {
  try {
    const log = await weightController.getWeightLog(req.mapped_pk!, req.params.version)
    res.json({ data: log, error: null })
  } catch (err) {
    next(err)
  }
})

// POST /api/weight/:version - Add weight entry
weightRouter.post('/:version', async (req, res, next) => {
  try {
    const { date, kg } = req.body

    if (!date || typeof kg !== 'number') {
      return res.status(400).json({
        data: null,
        error: 'Missing date or kg in request body',
      })
    }

    const entry: WeightEntry = { date, kg }
    await weightController.addWeightEntry(req.mapped_pk!, req.params.version, entry)
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})

// DELETE /api/weight/:version/:date - Remove weight entry
weightRouter.delete('/:version/:date', async (req, res, next) => {
  try {
    await weightController.removeWeightEntry(req.mapped_pk!, req.params.version, req.params.date)
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})
