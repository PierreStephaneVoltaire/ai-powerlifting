import { Router } from 'express'

export const statsRouter = Router()

const FASTAPI_URL = 'http://if-agent-api:8000/api/health/stats'

statsRouter.get('/categories', async (req, res, next) => {
  try {
    const url = new URL(`${FASTAPI_URL}/categories`)
    if (req.mapped_pk) url.searchParams.set('pk', req.mapped_pk)
    const response = await fetch(url.toString())
    if (!response.ok) {
      const body = await response.json().catch(() => ({ detail: response.statusText }))
      return res.status(response.status).json(body)
    }
    const data = await response.json()
    res.json(data)
  } catch (error) {
    next(error)
  }
})

statsRouter.post('/analyze', async (req, res, next) => {
  try {
    const response = await fetch(`${FASTAPI_URL}/analyze`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ ...req.body, pk: req.mapped_pk })
    })
    if (!response.ok) {
      const body = await response.json().catch(() => ({ detail: response.statusText }))
      return res.status(response.status).json(body)
    }
    const data = await response.json()
    res.json(data)
  } catch (error) {
    next(error)
  }
})
