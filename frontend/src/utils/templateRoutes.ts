export function templateDetailRoute(sk: string): string {
  return `/designer/template?sk=${encodeURIComponent(sk)}`
}

export function templateEditRoute(sk: string): string {
  return `/designer/template/edit?sk=${encodeURIComponent(sk)}`
}
