import { Router } from 'express'
import { getCurrentProfileHandler, getProfileHandler, searchProfilesHandler } from '../controllers/profilesController'

export const profilesRouter = Router()

profilesRouter.get('/search', searchProfilesHandler)
profilesRouter.get('/current', getCurrentProfileHandler)
profilesRouter.get('/:nickname', getProfileHandler)
