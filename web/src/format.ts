const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' })

/** Orders `seed-2` before `seed-10`. */
export function naturalCompare(a: string, b: string): number {
  return collator.compare(a, b)
}

export function formatCount(value: number): string {
  const abs = Math.abs(value)
  if (abs < 1e4)
    return String(Math.round(value))
  for (const [size, unit] of [[1e9, 'G'], [1e6, 'M'], [1e3, 'k']] as const) {
    if (abs >= size)
      return `${Number((value / size).toPrecision(3))}${unit}`
  }
  return String(value)
}

export function formatValue(value: number): string {
  if (!Number.isFinite(value))
    return String(value)
  const abs = Math.abs(value)
  if (abs !== 0 && (abs >= 1e6 || abs < 1e-3))
    return value.toExponential(2)
  return String(Number(value.toPrecision(4)))
}

export function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.round(seconds))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  if (h > 0)
    return `${h}h ${String(m).padStart(2, '0')}m`
  if (m > 0)
    return `${m}m ${String(s).padStart(2, '0')}s`
  return `${s}s`
}

export function formatClock(wall: number): string {
  return new Date(wall * 1000).toLocaleTimeString(undefined, { hour12: false })
}

export function formatDateTime(wall: number): string {
  return new Date(wall * 1000).toLocaleString(undefined, { hour12: false })
}
