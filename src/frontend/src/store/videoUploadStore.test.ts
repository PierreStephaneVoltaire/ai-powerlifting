import { beforeEach, describe, expect, it } from 'vitest'
import { activeUploads, overallProgress, useVideoUploadStore, type BackgroundUpload } from './videoUploadStore'

const file = (name: string, size: number) => new File([new Uint8Array(size)], name)

describe('video upload tracking', () => {
  beforeEach(() => useVideoUploadStore.setState({ uploads: [] }))

  it('weights the overall percentage by file size', () => {
    const uploads = [
      { id: 'a', fileName: 'a', size: 300, status: 'uploading', progress: 100 },
      { id: 'b', fileName: 'b', size: 100, status: 'uploading', progress: 0 },
    ] as BackgroundUpload[]
    expect(overallProgress(uploads)).toBe(75)
    expect(overallProgress([])).toBe(0)
  })

  it('shows an upload while it runs, keeps session uploads as done and drops the rest', async () => {
    const store = useVideoUploadStore.getState()
    let report: (progress: number) => void = () => {}
    let finish: () => void = () => {}
    const running = store.track({ id: 'session', file: file('squat.mp4', 10), sessionDate: '2026-11-02' }, (onProgress) => {
      report = onProgress
      return new Promise<string>((resolve) => { finish = () => resolve('ok') })
    })
    report(40)
    expect(activeUploads(useVideoUploadStore.getState().uploads).map((upload) => [upload.fileName, upload.progress])).toEqual([['squat.mp4', 40]])
    finish()
    await expect(running).resolves.toBe('ok')
    expect(useVideoUploadStore.getState().uploads).toMatchObject([{ id: 'session', status: 'done', progress: 100 }])
    expect(activeUploads(useVideoUploadStore.getState().uploads)).toEqual([])

    await store.track({ id: 'form', file: file('front.mov', 5) }, async () => 'ok')
    expect(useVideoUploadStore.getState().uploads.map((upload) => upload.id)).toEqual(['session'])
  })

  it('removes a failed upload', async () => {
    await expect(useVideoUploadStore.getState().track({ id: 'bad', file: file('x.mp4', 1), sessionDate: '2026-11-02' }, async () => { throw new Error('network') })).rejects.toThrow('network')
    expect(useVideoUploadStore.getState().uploads).toEqual([])
  })
})
