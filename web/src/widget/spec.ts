/**
 * The chart a Python process describes (`tuffbird.charts.chart_spec`), and the points it appends
 * while runs write. Series are plain arrays that appends grow in place; a version number tells the
 * view when to read them again, as on the board.
 */
import type { WireNumber } from '../api'
import { toNumber } from '../api'

type WirePoint = [step: number, value: WireNumber]

export interface ChartSpec {
  version: number
  title: string
  smoothing: number
  showRaw: boolean
  logX: boolean
  height: number
  panels: Array<{
    tag: string
    curves: Array<{ key: string, name: string, color: string, runs: Array<{ id: string, points: WirePoint[] }> }>
  }>
}

export interface AppendMessage {
  type: 'append'
  /** `start` is how many of the run's points the kernel had sent before these. */
  items: Array<{ tag: string, key: string, run: string, start: number, points: WirePoint[] }>
}

export interface Series {
  id: string
  /** `[step, value]` pairs, the shape TxLearningCurve takes. */
  points: Array<[number, number]>
}

export interface Curve {
  key: string
  name: string
  color: string
  runs: Series[]
}

export interface Panel {
  tag: string
  curves: Curve[]
}

export interface Chart {
  title: string
  smoothing: number
  showRaw: boolean
  logX: boolean
  height: number
  panels: Panel[]
}

function readPoints(points: WirePoint[]): Array<[number, number]> {
  return points.map(([step, value]) => [step, toNumber(value)])
}

export function readSpec(spec: ChartSpec): Chart {
  return {
    title: spec.title,
    smoothing: spec.smoothing,
    showRaw: spec.showRaw,
    logX: spec.logX,
    height: spec.height,
    panels: spec.panels.map(panel => ({
      tag: panel.tag,
      curves: panel.curves.map(curve => ({
        key: curve.key,
        name: curve.name,
        color: curve.color,
        runs: curve.runs.map(run => ({ id: run.id, points: readPoints(run.points) })),
      })),
    })),
  }
}

export function isAppend(message: unknown): message is AppendMessage {
  return typeof message === 'object' && message !== null && (message as AppendMessage).type === 'append'
}

/**
 * Adds appended points to their series. `gap` is set when the chart has missed points, as a view
 * restored after a reload or drawn after the first messages has: the kernel then sends a new spec.
 */
export function appendPoints(chart: Chart, message: AppendMessage): { landed: boolean, gap: boolean } {
  let landed = false
  let gap = false
  for (const item of message.items) {
    const curve = chart.panels.find(panel => panel.tag === item.tag)?.curves.find(entry => entry.key === item.key)
    const series = curve?.runs.find(run => run.id === item.run)
    // A new curve or run comes in a new spec, so a series the chart lacks means the chart is behind.
    if (!series || item.start > series.points.length) {
      gap = true
      continue
    }
    const fresh = readPoints(item.points.slice(series.points.length - item.start))
    for (const point of fresh)
      series.points.push(point)
    landed ||= fresh.length > 0
  }
  return { landed, gap }
}
