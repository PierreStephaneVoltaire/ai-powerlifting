import { Router } from 'express'
import {
  getOnboardingStatusHandler,
  completeAthleteBasicsHandler,
  completeProfileHandler,
  setRoleHandler,
} from '../controllers/onboardingController'

export const onboardingRouter = Router()

onboardingRouter.get('/status', getOnboardingStatusHandler)
onboardingRouter.post('/athlete-basics', completeAthleteBasicsHandler)
onboardingRouter.post('/profile', completeProfileHandler)
onboardingRouter.post('/role', setRoleHandler)
