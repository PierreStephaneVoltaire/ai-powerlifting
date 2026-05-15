import { Router } from 'express'
import * as federationsController from '../controllers/federationsController'
import type { FederationLibrary } from '@powerlifting/types'

export const federationsRouter = Router()

federationsRouter.get('/', async (req, res, next) => {
  try {
    const library = await federationsController.getFederationLibrary(req.mapped_pk!)
    res.json({ data: library, error: null })
  } catch (err) {
    next(err)
  }
})

federationsRouter.put('/', async (req, res, next) => {
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
