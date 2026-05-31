import express from 'express'
import cors from 'cors'
import cookieParser from 'cookie-parser'
import pinoHttp from 'pino-http'
import { createProxyMiddleware } from 'http-proxy-middleware'
import { logger } from './utils/logger'
import { authRouter } from './routes/auth'
import { requireAuth, requireUserOptional, resolvePk } from './middleware/auth'
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

app.use(requireUserOptional)

app.use('/api/directives', requireAuth, resolvePk, createProxyMiddleware({
  target: IF_AGENT_API_URL,
  changeOrigin: true,
  // NOTE: No pathRewrite — Express 5 strips the mount path from req.url,
  // so the regex '^/api/directives' would never match. Instead we rewrite
  // the path in the proxyReq handler using req.originalUrl which is intact.
  on: {
    proxyReq: (proxyReq, req: express.Request) => {
      const mappedPk = (req as any).mapped_pk
      if (!mappedPk) {
        proxyReq.destroy(new Error('No mapped_pk resolved for authenticated user'))
        return
      }
      // req.originalUrl still has the full /api/directives/... path
      // Replace /api/directives with /v1/directives to match the agent API router
      const originalPath = req.originalUrl || '/'
      const targetPath = originalPath.replace(/^\/api\/directives/, '/v1/directives')
      const separator = targetPath.includes('?') ? '&' : '?'
      let newPath = `${targetPath}${separator}pk=${encodeURIComponent(mappedPk)}`
      // For list requests (GET / with no sub-path), always include global directives
      const isListRequest = /^\/api\/directives\/?$/.test(req.originalUrl.split('?')[0])
      if (isListRequest) {
        newPath += '&include_global=true'
      }
      proxyReq.path = newPath
    },
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