import { Router } from 'express'
import { discordLogin, discordCallback, getMe, logout } from '../controllers/authController'

export const authRouter = Router()

authRouter.get('/discord/login', discordLogin)
authRouter.get('/discord/callback', discordCallback)
authRouter.get('/me', getMe)
authRouter.post('/logout', logout)