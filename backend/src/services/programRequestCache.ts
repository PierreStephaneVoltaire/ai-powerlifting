const pending = new Map<string, Promise<unknown>>()

export function singleFlight<T>(key: string, load: () => Promise<T>): Promise<T> {
  const existing = pending.get(key)
  if (existing) return existing as Promise<T>
  const promise = load()
  pending.set(key, promise)
  void promise.then(
    () => pending.delete(key),
    () => pending.delete(key),
  )
  return promise
}
