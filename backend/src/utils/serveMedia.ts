import { GetObjectCommand, HeadObjectCommand, S3Client } from '@aws-sdk/client-s3'
import type { Request, Response } from 'express'
import { Readable } from 'node:stream'
import { pipeline } from 'node:stream/promises'

const s3 = new S3Client({ region: process.env.AWS_REGION || 'ca-central-1' })

export function mediaRange(value: string, size: number): string | null {
  const match = /^bytes=(\d*)-(\d*)$/.exec(value)
  if (!match || (!match[1] && !match[2]) || size <= 0) return null
  const start = match[1] ? Number(match[1]) : Math.max(0, size - Number(match[2]))
  const end = match[1] && match[2] ? Math.min(size - 1, Number(match[2])) : size - 1
  if (!Number.isSafeInteger(start) || !Number.isSafeInteger(end) || start > end || start >= size) return null
  return `bytes=${start}-${end}`
}

export async function serveStoredMedia(req: Request, res: Response, bucket: string, key: string): Promise<void> {
  res.setHeader('Cache-Control', 'private, no-store')
  res.setHeader('Accept-Ranges', 'bytes')
  res.setHeader('X-Content-Type-Options', 'nosniff')
  const head = await s3.send(new HeadObjectCommand({ Bucket: bucket, Key: key }))
  const range = req.headers.range ? mediaRange(req.headers.range, head.ContentLength ?? 0) : undefined
  if (range === null) {
    res.status(416).setHeader('Content-Range', `bytes */${head.ContentLength ?? 0}`)
    res.end()
    return
  }
  if (head.ContentType) res.type(head.ContentType)
  if (head.ETag) res.setHeader('ETag', head.ETag)
  if (head.LastModified) res.setHeader('Last-Modified', head.LastModified.toUTCString())
  if (req.method === 'HEAD') {
    if (head.ContentLength !== undefined) res.setHeader('Content-Length', head.ContentLength)
    res.end()
    return
  }
  const object = await s3.send(new GetObjectCommand({ Bucket: bucket, Key: key, ...(range ? { Range: range } : {}) }))
  res.status(range ? 206 : 200)
  if (object.ContentLength !== undefined) res.setHeader('Content-Length', object.ContentLength)
  if (object.ContentRange) res.setHeader('Content-Range', object.ContentRange)
  if (!(object.Body instanceof Readable)) throw new Error('Storage returned no readable media')
  await pipeline(object.Body, res)
}
