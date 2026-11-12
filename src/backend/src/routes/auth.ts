import { Router } from 'express'
import { listProviders, getMe, logout } from '../controllers/authController'
import { requireUserOptional, resolvePk } from '../middleware/auth'

export const authRouter = Router()

authRouter.get('/providers', listProviders)
authRouter.get('/me', requireUserOptional, resolvePk, getMe)
authRouter.post('/logout', logout)
