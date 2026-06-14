import { Router } from 'express'
import * as dietNotesController from '../controllers/dietNotesController'
import type { DietNote } from '@powerlifting/types'

export const dietNotesRouter = Router({ mergeParams: true })

// GET /api/diet-notes/:version - Get diet notes
dietNotesRouter.get('/:version', async (req, res, next) => {
  try {
    const notes = await dietNotesController.getDietNotes(req.mapped_pk!, req.params.version)
    res.json({ data: notes, error: null })
  } catch (err) {
    next(err)
  }
})

// PUT /api/diet-notes/:version - Update all diet notes
dietNotesRouter.put('/:version', async (req, res, next) => {
  try {
    const { dietNotes } = req.body

    if (!Array.isArray(dietNotes)) {
      return res.status(400).json({
        data: null,
        error: 'dietNotes must be an array',
      })
    }

    await dietNotesController.updateDietNotes(
      req.mapped_pk!,
      req.params.version,
      dietNotes as DietNote[]
    )
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})
