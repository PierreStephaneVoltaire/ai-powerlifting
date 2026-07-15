import { Router } from 'express'
import {
  discordLogin,
  discordCallback,
  authentikLogin,
  authentikCallback,
  listProviders,
  getMe,
  logout,
} from '../controllers/authController'
import { requireUserOptional, resolvePk } from '../middleware/auth'
import { invalidateAllForUser } from '../utils/cache'

export const authRouter = Router()

authRouter.get('/providers', listProviders)
authRouter.get('/discord/login', discordLogin)
authRouter.get('/discord/callback', discordCallback)
authRouter.get('/authentik/login', authentikLogin)
authRouter.get('/authentik/callback', authentikCallback)
authRouter.get('/me', requireUserOptional, resolvePk, getMe)
authRouter.post('/logout', logout, async (req, res) => {
  if (req.mapped_pk) {
    await invalidateAllForUser(req.mapped_pk)
  }
  res.json({ ok: true })
})

