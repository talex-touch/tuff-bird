/** The board server's HTTP API: one snapshot, then a stream of what changed since it. */

export type RunStatus = 'running' | 'idle' | 'finished' | 'failed' | 'stopped'

export interface RunMeta {
  id: string
  name: string
  parent: string
  group: string
  status: RunStatus | string
  startTime: number | null
  endTime: number | null
  lastWall: number | null
  lastWrite: number
  hparams: Record<string, unknown>
  scalarTags: string[]
  textTags: string[]
  mediaTags: string[]
  files: string[]
}

/** NaN and infinities arrive as strings, since JSON has no way to write them. */
export type WireNumber = number | string
export type WirePoint = [step: number, value: WireNumber, wall: number]
export type WireText = [step: number, wall: number, text: string]

export interface Snapshot {
  /** Which board process this is; its sequence numbers mean nothing to another one. */
  board: string
  seq: number
  logdir: string
  runs: RunMeta[]
  scalars: Record<string, Record<string, WirePoint[]>>
  texts: Record<string, Record<string, WireText[]>>
}

export type Delta = { seq: number } & (
  | { type: 'run', run: RunMeta }
  | { type: 'scalars', run: string, tag: string, points: WirePoint[] }
  | { type: 'text', run: string, tag: string, items: WireText[] }
)

export function toNumber(value: WireNumber): number {
  return typeof value === 'number' ? value : Number(value)
}

export async function fetchSnapshot(): Promise<Snapshot> {
  // Relative, so the board also works behind a proxy that serves it under a sub-path.
  const response = await fetch('api/snapshot', { cache: 'no-store' })
  if (!response.ok)
    throw new Error(`snapshot: HTTP ${response.status}`)
  return response.json() as Promise<Snapshot>
}

export interface StreamHandlers {
  since: () => { board: string, seq: number }
  onDeltas: (deltas: Delta[]) => void
  /**
   * The board cannot resume from `since` (it restarted, or the page fell too far behind): load a
   * fresh snapshot. The stream reopens once the returned promise resolves.
   */
  onReset: () => Promise<void>
  onState: (state: 'live' | 'reconnecting') => void
}

/** Follows `/api/stream`, reconnecting with backoff; returns a function that stops it. */
export function followStream(handlers: StreamHandlers): () => void {
  let source: EventSource | null = null
  let retry = 0
  let timer = 0
  let stopped = false
  let batch: Delta[] = []
  let flushQueued = false

  const flush = (): void => {
    flushQueued = false
    const deltas = batch
    batch = []
    if (deltas.length)
      handlers.onDeltas(deltas)
  }

  const backoff = (): number => Math.min(8000, 500 * 2 ** retry++)

  const resync = (): void => {
    if (stopped)
      return
    handlers.onReset().then(open, () => {
      timer = window.setTimeout(resync, backoff())
    })
  }

  const open = (): void => {
    if (stopped)
      return
    // The server resumes from the query string, so the browser's own retry (which would replay
    // the original `since`) is replaced by ours.
    const { board, seq } = handlers.since()
    source = new EventSource(`api/stream?since=${seq}&board=${encodeURIComponent(board)}`)
    source.onopen = () => {
      retry = 0
      handlers.onState('live')
    }
    source.onmessage = (event: MessageEvent<string>) => {
      batch.push(JSON.parse(event.data) as Delta)
      if (!flushQueued) {
        flushQueued = true
        queueMicrotask(flush)
      }
    }
    source.addEventListener('reset', () => {
      source?.close()
      source = null
      flush()
      handlers.onState('reconnecting')
      resync()
    })
    source.onerror = () => {
      source?.close()
      source = null
      if (stopped)
        return
      flush()
      handlers.onState('reconnecting')
      timer = window.setTimeout(open, backoff())
    }
  }

  open()
  return () => {
    stopped = true
    window.clearTimeout(timer)
    source?.close()
  }
}
