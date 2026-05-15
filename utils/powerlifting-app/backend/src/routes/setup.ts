import { Router } from 'express'
import * as setupController from '../controllers/setupController'

export const setupRouter = Router()

setupRouter.get('/status', async (req, res, next) => {
  try {
    await setupController.getSetupStatus(req, res)
  } catch (err) {
    next(err)
  }
})

setupRouter.post('/initialize', async (req, res, next) => {
  try {
    await setupController.initializeSetup(req, res)
  } catch (err) {
    next(err)
  }
})
