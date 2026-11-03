import { Router } from 'express'
import {
  discordLogin,
  discordCallbackRoute,
  authentikLogin,
  authentikCallbackRoute,
  listProviders,
  getMe,
  logout,
} from '../controllers/authController'
import { requireUserOptional, resolvePk } from '../middleware/auth'

export const authRouter = Router()

authRouter.get('/providers', listProviders)
authRouter.get('/discord/login', discordLogin)
authRouter.get('/discord/callback', discordCallbackRoute)
authRouter.get('/authentik/login', authentikLogin)
authRouter.get('/authentik/callback', authentikCallbackRoute)
authRouter.get('/me', requireUserOptional, resolvePk, getMe)
authRouter.post('/logout', logout)
