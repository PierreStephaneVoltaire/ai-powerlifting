import { Router } from 'express'
import * as controller from '../controllers/authoredNotesController'

export const authoredNotesRouter = Router()

authoredNotesRouter.get('/private', async (_req, res, next) => {
  try {
    res.json({ data: await controller.listPrivateNotes(), error: null })
  } catch (error) {
    next(error)
  }
})

authoredNotesRouter.put('/private', async (req, res, next) => {
  try {
    res.json({ data: await controller.savePrivateNote(req.body), error: null })
  } catch (error) {
    next(error)
  }
})

authoredNotesRouter.get('/attachments/:context_domain', async (req, res, next) => {
  try {
    res.json({ data: await controller.listAttachments(req.params.context_domain as controller.NoteAttachment['context_domain'], typeof req.query.context_id === 'string' ? req.query.context_id : undefined), error: null })
  } catch (error) {
    next(error)
  }
})

authoredNotesRouter.post('/share', async (req, res, next) => {
  try {
    res.json({ data: await controller.shareNote(req.body), error: null })
  } catch (error) {
    next(error)
  }
})

authoredNotesRouter.post('/detach', async (req, res, next) => {
  try {
    res.json({ data: await controller.detachNote(req.body), error: null })
  } catch (error) {
    next(error)
  }
})
