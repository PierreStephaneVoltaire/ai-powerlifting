import { Router } from 'express'
import * as federationsController from '../controllers/federationsController'
import type { FederationLibrary } from '@powerlifting/types'

export const federationsRouter = Router()

// ─── New unversioned route: list user federations ──────────────────────────
federationsRouter.get('/', async (req, res, next) => {
  try {
    // If the client sends ?format=library, return the legacy FederationLibrary shape
    const format = req.query.format as string | undefined
    if (format === 'library') {
      const library = await federationsController.getFederationLibrary(req.mapped_pk!)
      res.json({ data: library, error: null })
    } else {
      const feds = await federationsController.listUserFederations(req.mapped_pk!)
      res.json({ data: feds, error: null })
    }
  } catch (err) {
    next(err)
  }
})

// PATCH /api/federations/:masterId - Patch a single federation (user_status + notes only)
federationsRouter.patch('/:masterId', async (req, res, next) => {
  try {
    const { user_status, notes } = req.body
    const updates: { user_status?: 'active' | 'archived'; notes?: string } = {}
    if (user_status === 'active' || user_status === 'archived') updates.user_status = user_status
    if (typeof notes === 'string') updates.notes = notes

    if (!updates.user_status && updates.notes === undefined) {
      return res.status(400).json({ data: null, error: 'No valid fields to update' })
    }

    await federationsController.patchUserFederation(req.mapped_pk!, req.params.masterId, updates)
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})

// ─── Legacy route: full library write ──────────────────────────────────────
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
