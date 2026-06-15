import { Router } from 'express'
import * as federationsController from '../controllers/federationsController'
import { requireAdmin } from '../middleware/auth'
import type { FederationLibrary } from '@powerlifting/types'

export const federationsRouter = Router()

federationsRouter.get('/', async (req, res, next) => {
  try {
    const format = req.query.format as string | undefined
    if (format === 'library') {
      const library = await federationsController.getFederationLibrary(req.mapped_pk!)
      res.json({ data: library, error: null })
    } else {
      const feds = await federationsController.listFederations()
      res.json({ data: feds, error: null })
    }
  } catch (err) {
    next(err)
  }
})

federationsRouter.put('/:masterId', requireAdmin, async (req, res, next) => {
  try {
    await federationsController.updateFederation(req.params.masterId, req.body)
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})

federationsRouter.put('/', requireAdmin, async (req, res, next) => {
  try {
    const { library } = req.body as { library: FederationLibrary }

    if (!library || !Array.isArray(library.federations) || !Array.isArray(library.qualification_standards)) {
      return res.status(400).json({
        data: null,
        error: 'library must include federations[] and qualification_standards[]',
      })
    }

    const nextLibrary = await federationsController.updateFederationLibrary(req.mapped_pk!, {
      federations: library.federations,
      qualification_standards: library.qualification_standards,
    })
    res.json({ data: nextLibrary, error: null })
  } catch (err) {
    next(err)
  }
})
