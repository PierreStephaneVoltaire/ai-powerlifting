import assert from 'node:assert/strict'
import { beforeEach, test } from 'node:test'
import { activeUploads, overallProgress, useVideoUploadStore, type BackgroundUpload } from './videoUploadStore'

const file = (name: string, size: number) => new File([new Uint8Array(size)], name)

beforeEach(() => useVideoUploadStore.setState({ uploads: [] }))

test('weights the overall percentage by file size', () => {
  const uploads = [
    { id: 'a', fileName: 'a', size: 300, status: 'uploading', progress: 100 },
    { id: 'b', fileName: 'b', size: 100, status: 'uploading', progress: 0 },
  ] as BackgroundUpload[]
  assert.equal(overallProgress(uploads), 75)
  assert.equal(overallProgress([]), 0)
})

test('shows an upload while it runs, keeps session uploads as done and drops the rest', async () => {
  const store = useVideoUploadStore.getState()
  let report: (progress: number) => void = () => {}
  let finish: () => void = () => {}
  const running = store.track({ id: 'session', file: file('squat.mp4', 10), sessionDate: '2026-11-02' }, (onProgress) => {
    report = onProgress
    return new Promise<string>((resolve) => { finish = () => resolve('ok') })
  })
  report(40)
  assert.deepEqual(activeUploads(useVideoUploadStore.getState().uploads).map((upload) => [upload.fileName, upload.progress]), [['squat.mp4', 40]])
  finish()
  assert.equal(await running, 'ok')
  const [done] = useVideoUploadStore.getState().uploads
  assert.equal(done.status, 'done')
  assert.equal(done.progress, 100)
  assert.deepEqual(activeUploads(useVideoUploadStore.getState().uploads), [])

  await store.track({ id: 'form', file: file('front.mov', 5) }, async () => 'ok')
  assert.deepEqual(useVideoUploadStore.getState().uploads.map((upload) => upload.id), ['session'])
})

test('removes a failed upload', async () => {
  await assert.rejects(useVideoUploadStore.getState().track({ id: 'bad', file: file('x.mp4', 1), sessionDate: '2026-11-02' }, async () => { throw new Error('network') }), /network/)
  assert.deepEqual(useVideoUploadStore.getState().uploads, [])
})
