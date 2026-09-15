import { Router } from 'express'
import {
  listGrantsHandler,
  checkGrantHandler,
} from '../controllers/grantsController'
import { requireWriteAuth } from '../middleware/auth'
import {
  favoriteHandler,
  favoritesHandler,
  listRelationshipsHandler,
  notificationsHandler,
  notificationsReadHandler,
  requestRelationshipHandler,
  respondRelationshipHandler,
  relationshipHistoryHandler,
  revokeRelationshipHandler,
} from '../controllers/relationshipsController'

export const grantsRouter = Router()

grantsRouter.get('/', listGrantsHandler)
grantsRouter.get('/check', checkGrantHandler)
grantsRouter.post('/requests', requireWriteAuth, requestRelationshipHandler)
grantsRouter.get('/requests', listRelationshipsHandler)
grantsRouter.post('/requests/respond', requireWriteAuth, respondRelationshipHandler)
grantsRouter.post('/requests/revoke', requireWriteAuth, revokeRelationshipHandler)
grantsRouter.get('/requests/history', relationshipHistoryHandler)
grantsRouter.post('/favorites', requireWriteAuth, favoriteHandler)
grantsRouter.get('/favorites', favoritesHandler)
grantsRouter.get('/notifications', notificationsHandler)
grantsRouter.post('/notifications/read', requireWriteAuth, notificationsReadHandler)
