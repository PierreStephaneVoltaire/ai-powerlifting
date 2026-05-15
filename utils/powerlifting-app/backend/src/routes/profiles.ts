import { Router } from 'express'
import { getProfileHandler, searchProfilesHandler } from '../controllers/profilesController'

export const profilesRouter = Router()

profilesRouter.get('/search', searchProfilesHandler)
profilesRouter.get('/:nickname', getProfileHandler)
