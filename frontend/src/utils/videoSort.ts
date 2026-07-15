import type { VideoLibraryItem, VideoSort } from '@powerlifting/types'

export type { VideoSort }

export const VIDEO_SORTS: Array<{ value: VideoSort; label: string }> = [
  { value: 'newest', label: 'Newest' },
  { value: 'oldest', label: 'Oldest' },
  { value: 'volume', label: 'Volume' },
  { value: 'weight', label: 'Max weight' },
]

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
  const aDate = typeof a?.session_date === 'string' ? a.session_date : ''
  const bDate = typeof b?.session_date === 'string' ? b.session_date : ''
  const aUploaded = typeof a?.video?.uploaded_at === 'string' ? a.video.uploaded_at : ''
  const bUploaded = typeof b?.video?.uploaded_at === 'string' ? b.video.uploaded_at : ''
  const cmp = aDate.localeCompare(bDate)
    || aUploaded.localeCompare(bUploaded)
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

export function sortVideos(videos: VideoLibraryItem[], sort: VideoSort): VideoLibraryItem[] {
  const comparator = COMPARATORS[sort] ?? compareNewest
  return videos.slice().sort(comparator)
}
