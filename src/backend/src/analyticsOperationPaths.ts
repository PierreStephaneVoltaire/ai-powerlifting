export function blocksGetPath(args: Record<string, unknown>): string {
  return `/blocks/${encodeURIComponent(String(args.blockKey || ''))}/analysis?refresh=${args.refresh === true}&cacheOnly=${args.cacheOnly === true}`
}
