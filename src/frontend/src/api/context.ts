let athlete = 'operator'
let person = ''

export function setRequestAthlete(value: string): void { athlete = value }
export function requestAthlete(): string { return athlete }
export function setRequestPerson(value: string): void { person = value }
export function requestPerson(): string { return person }
export function requestPartition(): string { return JSON.stringify([person, athlete]) }
