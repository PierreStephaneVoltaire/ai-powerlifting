import { Router } from 'express'
import { discordLogin, discordCallback, getMe, logout } from '../controllers/authController'
import { requireUserOptional } from '../middleware/auth'

export const authRouter = Router()

authRouter.get('/discord/login', discordLogin)
authRouter.get('/discord/callback', discordCallback)
authRouter.get('/me', requireUserOptional, getMe)
authRouter.post('/logout', logout)