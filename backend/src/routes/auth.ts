import { Router } from 'express'
import { discordLogin, discordCallback, getMe, logout } from '../controllers/authController'
import { requireUserOptional, resolvePk } from '../middleware/auth'
import { invalidateAllForUser } from '../utils/cache'

export const authRouter = Router()

authRouter.get('/discord/login', discordLogin)
authRouter.get('/discord/callback', discordCallback)
authRouter.get('/me', requireUserOptional, resolvePk, getMe)
authRouter.post('/logout', logout, async (req, res) => {
  if (req.mapped_pk) {
    await invalidateAllForUser(req.mapped_pk)
  }
  res.json({ ok: true })
})
