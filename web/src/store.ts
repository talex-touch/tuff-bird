/**
 * The page's copy of the board: run metadata, every scalar series and text chunk, and the view
 * settings. Series live in plain maps and are never made reactive; a version number per tag
 * (and per run, for text) tells the views when to read them again.
 */
import { computed, reactive, ref, shallowRef, watch } from 'vue'
import type { Delta, RunMeta, Snapshot, WirePoint, WireText } from './api'
import { fetchSnapshot, followStream, toNumber } from './api'
import { naturalCompare } from './format'

export const SYS_PREFIX = 'sys/'

export interface Series {
  /** `[step, value]` pairs, the shape TxLearningCurve takes. */
  points: Array<[number, number]>
  walls: number[]
}

export interface TextChunk {
  step: number
  wall: number
  text: string
}

export const board = reactive({
  logdir: '',
  connection: 'loading' as 'loading' | 'live' | 'reconnecting' | 'error',
})

/** In the order the page first saw them, which is also the order of their colors. */
export const runs = shallowRef<RunMeta[]>([])
export const scalarTags = shallowRef<string[]>([])
export const tagVersion = reactive<Record<string, number>>({})
export const textVersion = reactive<Record<string, number>>({})
/** The newest step of each run, over its own metrics (not `sys/`). */
export const lastStep = reactive<Record<string, number>>({})

const runById = new Map<string, RunMeta>()
/** tag → run → series */
const scalars = new Map<string, Map<string, Series>>()
/** run → tag → chunks */
const texts = new Map<string, Map<string, TextChunk[]>>()
/** Kept across snapshot reloads, so a board restart does not repaint every run. */
const runSlots = new Map<string, number>()
/** Merged groups count their own colors from the first, so two groups are not drawn in slots 7 and 8. */
const groupSlots = new Map<string, number>()

let boardId = ''
let lastSeq = 0
const dirtyTags = new Set<string>()
const dirtyTexts = new Set<string>()
let runsDirty = false
let tagsDirty = false
let flushTimer = 0

// TuffEx's six categorical colors, then six more for boards with many runs.
const PALETTE = [
  'var(--tx-chart-categorical-1, #4290f0)',
  'var(--tx-chart-categorical-2, #f5b647)',
  'var(--tx-chart-categorical-3, #e8649d)',
  'var(--tx-chart-categorical-4, #8d58ee)',
  'var(--tx-chart-categorical-5, #50c3b6)',
  'var(--tx-chart-categorical-6, #d37536)',
  '#2f9e44',
  '#3b5bdb',
  '#c2255c',
  '#0c8599',
  '#82a31c',
  '#868e96',
]

export function colorOf(key: string): string {
  const slots = key.startsWith('group:') ? groupSlots : runSlots
  let slot = slots.get(key)
  if (slot === undefined) {
    slot = slots.size
    slots.set(key, slot)
  }
  return PALETTE[slot % PALETTE.length]
}

export function seriesOf(tag: string, run: string): Series | undefined {
  return scalars.get(tag)?.get(run)
}

export function textsOf(run: string): Map<string, TextChunk[]> | undefined {
  return texts.get(run)
}

// ------------------------------------------------------------------ ingest

function upsertRun(run: RunMeta): void {
  runById.set(run.id, run)
  runsDirty = true
}

function appendPoints(run: string, tag: string, wire: WirePoint[]): void {
  let byRun = scalars.get(tag)
  if (!byRun) {
    byRun = new Map()
    scalars.set(tag, byRun)
    tagsDirty = true
  }
  let series = byRun.get(run)
  if (!series) {
    series = { points: [], walls: [] }
    byRun.set(run, series)
  }
  let newest = lastStep[run] ?? Number.NEGATIVE_INFINITY
  for (const [step, value, wall] of wire) {
    series.points.push([step, toNumber(value)])
    series.walls.push(wall)
    newest = Math.max(newest, step)
  }
  if (!tag.startsWith(SYS_PREFIX) && newest !== lastStep[run])
    lastStep[run] = newest
  dirtyTags.add(tag)
}

function appendTexts(run: string, tag: string, wire: WireText[]): void {
  let byTag = texts.get(run)
  if (!byTag) {
    byTag = new Map()
    texts.set(run, byTag)
  }
  let chunks = byTag.get(tag)
  if (!chunks) {
    chunks = []
    byTag.set(tag, chunks)
  }
  for (const [step, wall, text] of wire)
    chunks.push({ step, wall, text })
  dirtyTexts.add(run)
}

/**
 * Older runs first, so the colors a page hands out on reload are the ones it handed out while it
 * watched new runs arrive. Runs started in the same second keep their id order, which puts the
 * seeds of one launch next to each other.
 */
function byStart(a: RunMeta, b: RunMeta): number {
  const second = (run: RunMeta): number => Math.floor(run.startTime ?? Number.MAX_SAFE_INTEGER)
  return second(a) - second(b) || naturalCompare(a.id, b.id)
}

function flush(): void {
  flushTimer = 0
  if (runsDirty) {
    runsDirty = false
    const known = new Set(runs.value.map(run => run.id))
    const added = [...runById.values()].filter(run => !known.has(run.id)).sort(byStart)
    for (const run of added) {
      colorOf(run.id)
      if (run.parent)
        colorOf(`group:${run.parent}`)
    }
    runs.value = [...runs.value.filter(run => runById.has(run.id)).map(run => runById.get(run.id)!), ...added]
  }
  if (tagsDirty) {
    tagsDirty = false
    scalarTags.value = [...scalars.keys()].sort(naturalCompare)
  }
  for (const tag of dirtyTags)
    tagVersion[tag] = (tagVersion[tag] ?? 0) + 1
  dirtyTags.clear()
  for (const run of dirtyTexts)
    textVersion[run] = (textVersion[run] ?? 0) + 1
  dirtyTexts.clear()
}

/** Charts redraw at most a few times a second, however fast the training writes. */
function scheduleFlush(): void {
  if (!flushTimer)
    flushTimer = window.setTimeout(flush, 150)
}

function applySnapshot(snapshot: Snapshot): void {
  boardId = snapshot.board
  lastSeq = snapshot.seq
  board.logdir = snapshot.logdir
  runById.clear()
  scalars.clear()
  texts.clear()
  for (const key of Object.keys(lastStep))
    delete lastStep[key]
  runs.value = []
  for (const run of snapshot.runs)
    upsertRun(run)
  for (const [run, tags] of Object.entries(snapshot.scalars)) {
    for (const [tag, points] of Object.entries(tags))
      appendPoints(run, tag, points)
  }
  for (const [run, tags] of Object.entries(snapshot.texts)) {
    for (const [tag, items] of Object.entries(tags))
      appendTexts(run, tag, items)
  }
  for (const tag of Object.keys(tagVersion))
    dirtyTags.add(tag)
  for (const run of Object.keys(textVersion))
    dirtyTexts.add(run)
  tagsDirty = true
  runsDirty = true
  window.clearTimeout(flushTimer)
  flush()
}

function applyDeltas(deltas: Delta[]): void {
  for (const delta of deltas) {
    if (delta.seq <= lastSeq)
      continue
    lastSeq = delta.seq
    if (delta.type === 'run')
      upsertRun(delta.run)
    else if (delta.type === 'scalars')
      appendPoints(delta.run, delta.tag, delta.points)
    else if (delta.type === 'text')
      appendTexts(delta.run, delta.tag, delta.items)
  }
  scheduleFlush()
}

export async function connect(): Promise<void> {
  try {
    applySnapshot(await fetchSnapshot())
  }
  catch {
    board.connection = 'error'
    window.setTimeout(connect, 3000)
    return
  }
  followStream({
    since: () => ({ board: boardId, seq: lastSeq }),
    onDeltas: applyDeltas,
    onReset: async () => applySnapshot(await fetchSnapshot()),
    onState: (state) => {
      board.connection = state
    },
  })
}

// ------------------------------------------------------------------ view settings

const PREFS_KEY = 'tuffbird:prefs'

function loadPrefs(): Record<string, unknown> {
  try {
    return JSON.parse(localStorage.getItem(PREFS_KEY) ?? '{}') as Record<string, unknown>
  }
  catch {
    return {}
  }
}

const saved = loadPrefs()

export const prefs = reactive({
  view: (saved.view as string) ?? 'scalars',
  smoothing: typeof saved.smoothing === 'number' ? saved.smoothing : 0.6,
  showRaw: saved.showRaw !== false,
  mergeGroups: saved.mergeGroups === true,
  logX: saved.logX === true,
})

watch(prefs, value => localStorage.setItem(PREFS_KEY, JSON.stringify(value)), { deep: true })

export const ui = reactive({
  hidden: new Set<string>(),
  /** The run (or merged group) under the pointer in the run list, emphasized in every chart. */
  highlighted: null as string | null,
  /** The run whose output the output view shows. */
  focused: null as string | null,
  runFilter: '',
  tagFilter: '',
})

/** Ticks once a second, for elapsed times and the running → idle decay. */
export const now = ref(Date.now() / 1000)
window.setInterval(() => {
  now.value = Date.now() / 1000
}, 1000)

// ------------------------------------------------------------------ derived

function commonPrefix(ids: string[]): string[] {
  if (ids.length < 2)
    return []
  const split = ids.map(id => id.split('/'))
  const prefix: string[] = []
  for (let index = 0; ; index++) {
    const part = split[0][index]
    // Never strip a run's own name, only the directories every run shares.
    if (part === undefined || split.some(parts => parts.length <= index + 1 || parts[index] !== part))
      break
    prefix.push(part)
  }
  return prefix
}

/** Run ids without the directories every run shares: `cartpole/lr-3e-3/seed-0` → `lr-3e-3/seed-0`. */
export const runLabels = computed(() => {
  const prefix = commonPrefix(runs.value.map(run => run.id))
  const labels = new Map<string, string>()
  for (const run of runs.value)
    labels.set(run.id, run.id === '.' ? run.name : run.id.split('/').slice(prefix.length).join('/'))
  return labels
})

export interface RunGroup {
  key: string
  label: string
  runs: RunMeta[]
}

/** Runs under the same directory form a group: the seeds of one configuration. */
export const groups = computed<RunGroup[]>(() => {
  const prefix = commonPrefix(runs.value.map(run => run.id))
  const byKey = new Map<string, RunGroup>()
  for (const run of runs.value) {
    const key = run.parent
    let group = byKey.get(key)
    if (!group) {
      // When every run sits in this one directory, the shared prefix is the whole key.
      const label = key.split('/').slice(prefix.length).join('/') || key.split('/').pop() || key
      group = { key, label, runs: [] }
      byKey.set(key, group)
    }
    group.runs.push(run)
  }
  const list = [...byKey.values()]
  for (const group of list)
    group.runs.sort((a, b) => naturalCompare(a.id, b.id))
  return list.sort((a, b) => naturalCompare(a.key, b.key))
})

export const visibleRuns = computed(() => runs.value.filter(run => !ui.hidden.has(run.id)))

export const runningCount = computed(() => runs.value.filter(run => run.status === 'running').length)

/** What a run is drawn as: itself, or its group when groups are merged (top-level runs never merge). */
export function seriesKeyOf(run: RunMeta): string {
  return prefs.mergeGroups && run.parent ? `group:${run.parent}` : run.id
}
