import type { VideoSort } from '@powerlifting/types'

export function isVideoSort(value: unknown): value is VideoSort {
  return value === 'newest' || value === 'oldest' || value === 'volume' || value === 'weight'
}
