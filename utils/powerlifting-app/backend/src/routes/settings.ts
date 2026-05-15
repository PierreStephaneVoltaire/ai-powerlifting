import { Router } from 'express'
import { getSettingsHandler, updateNicknameHandler, updateProfileHandler } from '../controllers/settingsController'

export const settingsRouter = Router()

settingsRouter.get('/', getSettingsHandler)
settingsRouter.put('/nickname', updateNicknameHandler)
settingsRouter.put('/profile', updateProfileHandler)
