import express from 'express'
import cors from 'cors'
import cookieParser from 'cookie-parser'
import { programsRouter } from './routes/programs'
import { sessionsRouter } from './routes/sessions'
import { exercisesRouter } from './routes/exercises'
import { maxesRouter } from './routes/maxes'
import { weightRouter } from './routes/weight'
import { supplementsRouter } from './routes/supplements'
import { dietNotesRouter } from './routes/dietNotes'
import { competitionsRouter } from './routes/competitions'
import { videosRouter } from './routes/videos'
import { analyticsRouter } from './routes/analytics'
import { exportRouter } from './routes/export'
import { importRouter } from './routes/import'
import { templateRouter } from './routes/template'
import { statsRouter } from './routes/stats'
import { authRouter } from './routes/auth'
import { settingsRouter } from './routes/settings'
import { goalsRouter } from './routes/goals'
import { federationsRouter } from './routes/federations'
import { errorHandler } from './middleware/errorHandler'
import { requireUserOptional, resolvePk } from './middleware/auth'

const app = express()

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173'

// Middleware
app.use(cors({
  origin: FRONTEND_URL,
  credentials: true,
}))
app.use(cookieParser())
app.use(express.json())

// Health check
app.get('/health', (_req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() })
})

// Auth routes (before identity middleware — callback handles its own flow)
app.use('/api/auth', authRouter)

// Identity resolution for all domain routes
app.use(requireUserOptional, resolvePk)

// Domain routes
app.use('/api/settings', settingsRouter)
app.use('/api/programs', programsRouter)
app.use('/api/goals', goalsRouter)
app.use('/api/federations', federationsRouter)
app.use('/api/sessions', sessionsRouter)
app.use('/api/exercises', exercisesRouter)
app.use('/api/maxes', maxesRouter)
app.use('/api/weight', weightRouter)
app.use('/api/supplements', supplementsRouter)
app.use('/api/diet-notes', dietNotesRouter)
app.use('/api/competitions', competitionsRouter)
app.use('/api/videos', videosRouter)
app.use('/api/analytics', analyticsRouter)
app.use('/api/export', exportRouter)
app.use('/api/import', importRouter)
app.use('/api/templates', templateRouter)
app.use('/api/stats', statsRouter)

// Error handler
app.use(errorHandler)

// 404 handler
app.use((_req, res) => {
  res.status(404).json({
    data: null,
    error: 'Not found',
  })
})

const PORT = process.env.PORT || 3001

app.listen(PORT, () => {
  console.log(`Powerlifting API running on port ${PORT}`)
  console.log(`Health check: http://localhost:${PORT}/health`)
})
