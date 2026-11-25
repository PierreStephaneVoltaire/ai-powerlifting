import { Router } from 'express'
import * as dietNotesController from '../controllers/dietNotesController'
import { cacheGet, invalidateAfter } from '../utils/cacheMiddleware'
import type { DietNote } from '@powerlifting/types'

export const dietNotesRouter = Router({ mergeParams: true })

// GET /api/diet-notes/current - Get diet notes
dietNotesRouter.get('/current', cacheGet((req) => [`diet-notes:current`]), async (req, res, next) => {
  try {
    const notes = await dietNotesController.getDietNotes(req.mapped_pk!)
    res.json({ data: notes, error: null })
  } catch (err) {
    next(err)
  }
})

// PUT /api/diet-notes/current - Update all diet notes
dietNotesRouter.put('/current', invalidateAfter((req) => [`diet-notes:current`]), async (req, res, next) => {
  try {
    const { dietNotes } = req.body

    if (!Array.isArray(dietNotes)) {
      return res.status(400).json({
        data: null,
        error: 'dietNotes must be an array',
      })
    }

    const result = await dietNotesController.updateDietNotes(
      req.mapped_pk!,
      dietNotes as DietNote[]
    )
    res.json({ data: result, error: null })
  } catch (err) {
    next(err)
  }
})
