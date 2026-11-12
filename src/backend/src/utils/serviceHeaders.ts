export interface ServiceScope {
  athlete: string
  person: string
}

export function serviceHeaders(scope: ServiceScope): Record<string, string> {
  return { 'Content-Type': 'application/json', 'X-Person-Pk': scope.person, 'X-Athlete-Pk': scope.athlete }
}
