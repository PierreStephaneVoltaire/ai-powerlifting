import { Router } from 'express'
import { getCurrentProfileHandler, getProfileHandler, searchProfilesHandler } from '../controllers/profilesController'
import { callOperation } from '../utils/operations'
import { serveStoredMedia } from '../utils/serveMedia'

export const profilesRouter = Router()

profilesRouter.get(/^\/media\/(.+)$/, async (req, res, next) => {
  try {
    const media = await callOperation('profile_media_resolve', { s3_key: req.params[0] })
    await serveStoredMedia(req, res, process.env.VIDEOS_BUCKET || 'powerlifting-session-videos', media.s3_key)
  } catch (error) { next(error) }
})

profilesRouter.get('/search', searchProfilesHandler)
profilesRouter.get('/tags', async (req, res, next) => {
  try {
    const result = await callOperation('tag_catalog_get', {})
    res.json({ data: result.tags })
  } catch (error) { next(error) }
})
profilesRouter.get('/athlete/context', async (_req, res, next) => {
  try { res.json({ data: await callOperation('handler_context', {}) }) } catch (error) { next(error) }
})
profilesRouter.get('/current', getCurrentProfileHandler)
profilesRouter.get('/:nickname', getProfileHandler)
