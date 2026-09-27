import { MEDIA_FILTER_KEYS, type GraphLayersConfig } from './graphConfig'

export function mediaQueryParam(filter: GraphLayersConfig['mediaFilter']): string | null {
  const enabled = MEDIA_FILTER_KEYS.filter((key) => filter[key])
  if (enabled.length === MEDIA_FILTER_KEYS.length) return null
  return enabled.join(',')
}

export function startOfDayIso(date: Date): string {
  const next = new Date(date)
  next.setHours(0, 0, 0, 0)
  return next.toISOString()
}

export function endOfDayIso(date: Date): string {
  const next = new Date(date)
  next.setHours(23, 59, 59, 999)
  return next.toISOString()
}

export function isoToDate(value: string | null | undefined): Date | undefined {
  if (!value) return undefined
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? undefined : parsed
}
