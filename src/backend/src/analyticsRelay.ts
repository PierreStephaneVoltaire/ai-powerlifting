import type { Response } from 'express'

const RELAYED_HEADERS = ['content-type', 'content-disposition']

export async function relayResponse(upstream: globalThis.Response, res: Response): Promise<void> {
  const body = Buffer.from(await upstream.arrayBuffer())
  res.status(upstream.status)
  for (const name of RELAYED_HEADERS) {
    const value = upstream.headers.get(name)
    if (value) res.setHeader(name, value)
  }
  res.send(body)
}
