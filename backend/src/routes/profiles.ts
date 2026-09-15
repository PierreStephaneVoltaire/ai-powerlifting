import { Router } from 'express'
import { getCurrentProfileHandler, getProfileHandler, searchProfilesHandler } from '../controllers/profilesController'
import { invokeLambda } from '../utils/lambda'
import { serveStoredMedia } from '../utils/serveMedia'

export const profilesRouter = Router()

profilesRouter.get(/^\/media\/(.+)$/, async (req, res, next) => {
  try {
    const media = await invokeLambda('profile_media_resolve', { s3_key: req.params[0] })
    await serveStoredMedia(req, res, process.env.VIDEOS_BUCKET || 'powerlifting-session-videos', media.s3_key)
  } catch (error) { next(error) }
})

profilesRouter.get('/search', searchProfilesHandler)
profilesRouter.get('/tags', async (req, res, next) => {
  try {
    const result = await invokeLambda('tag_catalog_get', { include_pending: req.query.review === 'true' })
    res.json({ data: result.tags })
  } catch (error) { next(error) }
})
profilesRouter.get('/athlete/context', async (_req, res, next) => {
  try { res.json({ data: await invokeLambda('handler_context', {}) }) } catch (error) { next(error) }
})
profilesRouter.get('/current', getCurrentProfileHandler)
profilesRouter.get('/:nickname', getProfileHandler)
