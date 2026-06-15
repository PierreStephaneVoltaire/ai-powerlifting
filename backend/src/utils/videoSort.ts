import type { VideoLibraryItem, VideoSort } from '@powerlifting/types'

function safeNumber(value: number | null | undefined): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0
}

export function videoVolumeKg(item: VideoLibraryItem): number {
  const sets = safeNumber(item.exercise_sets)
  const reps = safeNumber(item.exercise_reps)
  const kg = safeNumber(item.exercise_kg)
  if (kg > 0) return sets * reps * kg
  return sets * reps
}

function compareNewest(a: VideoLibraryItem, b: VideoLibraryItem): number {
  const cmp = a.session_date.localeCompare(b.session_date)
    || a.video.uploaded_at.localeCompare(b.video.uploaded_at)
  return -cmp
}

function compareOldest(a: VideoLibraryItem, b: VideoLibraryItem): number {
  return -compareNewest(a, b)
}

function compareVolume(a: VideoLibraryItem, b: VideoLibraryItem): number {
  return videoVolumeKg(b) - videoVolumeKg(a)
    || safeNumber(b.exercise_kg) - safeNumber(a.exercise_kg)
    || compareNewest(a, b)
}

function compareWeight(a: VideoLibraryItem, b: VideoLibraryItem): number {
  return safeNumber(b.exercise_kg) - safeNumber(a.exercise_kg)
    || compareNewest(a, b)
}

const COMPARATORS: Record<VideoSort, (a: VideoLibraryItem, b: VideoLibraryItem) => number> = {
  newest: compareNewest,
  oldest: compareOldest,
  volume: compareVolume,
  weight: compareWeight,
}

export function isVideoSort(value: unknown): value is VideoSort {
  return value === 'newest' || value === 'oldest' || value === 'volume' || value === 'weight'
}

export function sortVideos(videos: VideoLibraryItem[], sort: VideoSort): VideoLibraryItem[] {
  const comparator = COMPARATORS[sort] ?? compareNewest
  return videos.slice().sort(comparator)
}
