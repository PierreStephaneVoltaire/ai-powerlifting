import express from 'express'
import cors from 'cors'
import cookieParser from 'cookie-parser'
import pinoHttp from 'pino-http'
import { logger } from './utils/logger'
import { programsRouter } from './routes/programs'
import { sessionsRouter } from './routes/sessions'
import { exercisesRouter } from './routes/exercises'
import { maxesRouter } from './routes/maxes'
import { weightRouter } from './routes/weight'
import { supplementsRouter } from './routes/supplements'
import { dietNotesRouter } from './routes/dietNotes'
import { blockNotesRouter } from './routes/blockNotes'
import { competitionsRouter } from './routes/competitions'
import { videosRouter } from './routes/videos'
import { analyticsRouter } from './routes/analytics'
import { exportRouter } from './routes/export'
import { importRouter } from './routes/import'
import { templateRouter } from './routes/template'
import { statsRouter } from './routes/stats'
import { authRouter } from './routes/auth'
import { settingsRouter } from './routes/settings'
import { profilesRouter } from './routes/profiles'
import { goalsRouter } from './routes/goals'
import { federationsRouter } from './routes/federations'
import { budgetRouter } from './routes/budget'
import { setupRouter } from './routes/setup'
import { grantsRouter } from './routes/grants'
import { errorHandler } from './middleware/errorHandler'
import { requireUserOptional, requireWriteAuth, resolvePk } from './middleware/auth'

const app = express()

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173'

app.use(pinoHttp({ logger }))

app.use(cors({
  origin: FRONTEND_URL,
  credentials: true,
}))
app.use(cookieParser())
app.use(express.json())

app.get('/health', (_req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() })
})

app.use('/api/auth', authRouter)

app.use(requireUserOptional, resolvePk)
app.use(requireWriteAuth)

app.use('/api/settings', settingsRouter)
app.use('/api/profiles', profilesRouter)
app.use('/api/setup', setupRouter)
app.use('/api/grants', grantsRouter)
app.use('/api/programs', programsRouter)
app.use('/api/goals', goalsRouter)
app.use('/api/federations', federationsRouter)
app.use('/api/budget', budgetRouter)
app.use('/api/sessions', sessionsRouter)
app.use('/api/exercises', exercisesRouter)
app.use('/api/maxes', maxesRouter)
app.use('/api/weight', weightRouter)
app.use('/api/supplements', supplementsRouter)
app.use('/api/diet-notes', dietNotesRouter)
app.use('/api/block-notes', blockNotesRouter)
app.use('/api/competitions', competitionsRouter)
app.use('/api/videos', videosRouter)
app.use('/api/analytics', analyticsRouter)
app.use('/api/export', exportRouter)
app.use('/api/import', importRouter)
app.use('/api/templates', templateRouter)
app.use('/api/stats', statsRouter)

app.use(errorHandler)

app.use((_req, res) => {
  res.status(404).json({
    data: null,
    error: 'Not found',
  })
})

const PORT = process.env.PORT || 3001

app.listen(PORT, () => {
  logger.info({ port: PORT, url: `http://localhost:${PORT}` }, 'Powerlifting API started')
})
