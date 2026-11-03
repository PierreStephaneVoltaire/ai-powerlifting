export function canApplyCompetitionRequest(
  startedPartition: string,
  startedRequest: number,
  currentPartition: string,
  currentRequest: number,
): boolean {
  return startedPartition === currentPartition && startedRequest === currentRequest
}
