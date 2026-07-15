import { Router } from 'express'
import {
  createGrantHandler,
  revokeGrantHandler,
  listGrantsHandler,
  checkGrantHandler,
} from '../controllers/grantsController'
import { requireWriteAuth } from '../middleware/auth'

export const grantsRouter = Router()

grantsRouter.get('/', listGrantsHandler)
grantsRouter.post('/', requireWriteAuth, createGrantHandler)
grantsRouter.delete('/', requireWriteAuth, revokeGrantHandler)
grantsRouter.get('/check', checkGrantHandler)
