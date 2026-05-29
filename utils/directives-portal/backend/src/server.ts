import express from 'express'
import cors from 'cors'
import cookieParser from 'cookie-parser'
import pinoHttp from 'pino-http'
import { createProxyMiddleware } from 'http-proxy-middleware'
import { logger } from './utils/logger'
import { authRouter } from './routes/auth'
import { requireAuth } from './middleware/auth'
import { errorHandler } from './middleware/errorHandler'

const app = express()

const PORT = process.env.PORT || '3006'
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173'
const IF_AGENT_API_URL = process.env.IF_AGENT_API_URL || 'http://if-agent-api:8000'

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

// Auth routes — no auth required
app.use('/api/auth', authRouter)

// All directive routes require authentication and are proxied to FastAPI
app.use('/api/directives', requireAuth, createProxyMiddleware({
  target: IF_AGENT_API_URL,
  changeOrigin: true,
  pathRewrite: {
    '^/api/directives': '/v1/directives',
  },
}))

app.use(errorHandler)

app.use((_req, res) => {
  res.status(404).json({
    data: null,
    error: 'Not found',
  })
})

app.listen(PORT, () => {
  logger.info({ port: PORT, url: `http://localhost:${PORT}` }, 'Directives Portal API started')
})

export default app