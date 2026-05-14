import { Router } from 'express'
import * as blockNotesController from '../controllers/blockNotesController'
import type { BlockNote } from '@powerlifting/types'

export const blockNotesRouter = Router({ mergeParams: true })

blockNotesRouter.get('/:version', async (req, res, next) => {
  try {
    const notes = await blockNotesController.getBlockNotes(req.effectivePk!, req.params.version)
    res.json({ data: notes, error: null })
  } catch (err) {
    next(err)
  }
})

blockNotesRouter.put('/:version', async (req, res, next) => {
  try {
    const { blockNotes } = req.body

    if (!Array.isArray(blockNotes)) {
      return res.status(400).json({
        data: null,
        error: 'blockNotes must be an array',
      })
    }

    await blockNotesController.updateBlockNotes(
      req.effectivePk!,
      req.params.version,
      blockNotes as BlockNote[]
    )
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})
