<script setup lang="ts">
import type { TextChunk } from '../store'
import { TxEmptyState } from '@talex-touch/tuffex/empty-state'
import { TxFlatRadio, TxFlatRadioItem } from '@talex-touch/tuffex/flat-radio'
import { TxSearchInput } from '@talex-touch/tuffex/search-input'
import { TxSwitch } from '@talex-touch/tuffex/switch'
import { computed, nextTick, ref, watch } from 'vue'
import { formatClock, formatCount } from '../format'
import { t } from '../i18n'
import { colorOf, runLabels, runs, textsOf, textVersion, ui } from '../store'

const TERMINAL = '\u0000terminal'
const STREAMS = new Set(['stdout', 'stderr'])
const MAX_LINES = 5000
// eslint-disable-next-line no-control-regex
const ANSI = /\x1B(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*\x07|[@-Z\\-_])/g

interface Line {
  id: number
  stream: string
  wall: number
  raw: string
}

const query = ref('')
const follow = ref(true)
const choice = ref(TERMINAL)
const pane = ref<HTMLElement>()

/** The run picked in the run list, else the one written to most recently. */
const run = computed(() => {
  const picked = ui.focused ? runs.value.find(item => item.id === ui.focused) : undefined
  return picked ?? [...runs.value].sort((a, b) => b.lastWrite - a.lastWrite)[0] ?? null
})

const otherTags = computed(() => {
  if (!run.value)
    return []
  void textVersion[run.value.id]
  return [...(textsOf(run.value.id)?.keys() ?? [])].filter(tag => !STREAMS.has(tag)).sort()
})

watch(run, () => {
  choice.value = TERMINAL
})

/** Keeps what a terminal would show after carriage returns, and a trailing one that is still pending. */
function collapse(text: string): string {
  if (!text.includes('\r'))
    return text
  const pending = text.endsWith('\r')
  const segments = text.split('\r').filter(Boolean)
  const last = segments[segments.length - 1] ?? ''
  return pending ? `${last}\r` : last
}

/** stdout and stderr interleaved by time and cut into lines; a chunk without a newline continues in the next. */
const lines = computed<Line[]>(() => {
  if (!run.value)
    return []
  void textVersion[run.value.id]
  const byTag = textsOf(run.value.id)
  const merged: Array<{ stream: string, chunk: TextChunk }> = []
  for (const stream of STREAMS) {
    for (const chunk of byTag?.get(stream) ?? [])
      merged.push({ stream, chunk })
  }
  merged.sort((a, b) => a.chunk.wall - b.chunk.wall)
  const list: Line[] = []
  const open = new Map<string, Line>()
  for (const { stream, chunk } of merged) {
    const parts = chunk.text.replace(ANSI, '').split('\n')
    for (let index = 0; index < parts.length; index++) {
      const part = parts[index]
      const isLast = index === parts.length - 1
      if (isLast && part === '') {
        open.delete(stream)
        break
      }
      let line = index === 0 ? open.get(stream) : undefined
      if (!line) {
        line = { id: list.length, stream, wall: chunk.wall, raw: '' }
        list.push(line)
      }
      line.raw = collapse(line.raw + part)
      if (isLast)
        open.set(stream, line)
      else
        open.delete(stream)
    }
  }
  return list
})

function display(line: Line): string {
  return line.raw.endsWith('\r') ? line.raw.slice(0, -1) : line.raw
}

const shownLines = computed(() => {
  const needle = query.value.trim().toLowerCase()
  const list = needle ? lines.value.filter(line => display(line).toLowerCase().includes(needle)) : lines.value
  return list.length > MAX_LINES ? list.slice(-MAX_LINES) : list
})

function segments(text: string): Array<{ text: string, hit: boolean }> {
  const needle = query.value.trim().toLowerCase()
  if (!needle)
    return [{ text, hit: false }]
  const out: Array<{ text: string, hit: boolean }> = []
  const lower = text.toLowerCase()
  let cursor = 0
  for (let at = lower.indexOf(needle); at !== -1; at = lower.indexOf(needle, cursor)) {
    if (at > cursor)
      out.push({ text: text.slice(cursor, at), hit: false })
    out.push({ text: text.slice(at, at + needle.length), hit: true })
    cursor = at + needle.length
  }
  if (cursor < text.length)
    out.push({ text: text.slice(cursor), hit: false })
  return out
}

const textChunks = computed(() => {
  if (!run.value || choice.value === TERMINAL)
    return []
  void textVersion[run.value.id]
  return textsOf(run.value.id)?.get(choice.value) ?? []
})

function onScroll(): void {
  const element = pane.value
  if (element)
    follow.value = element.scrollHeight - element.scrollTop - element.clientHeight < 24
}

watch([shownLines, textChunks, follow], async () => {
  if (!follow.value)
    return
  await nextTick()
  const element = pane.value
  if (element)
    element.scrollTop = element.scrollHeight
}, { flush: 'post' })
</script>

<template>
  <div class="output">
    <TxEmptyState v-if="!run" class="output__empty" variant="no-selection" :title="t.pickRun" size="small" />
    <template v-else>
      <div class="output__bar">
        <span class="output__run">
          <span class="swatch" :style="{ '--swatch': colorOf(run.id) }" />
          <span class="output__run-name" :title="run.id">{{ runLabels.get(run.id) ?? run.name }}</span>
          <span class="output__run-status" :class="`is-${run.status}`">{{ t.status[run.status] ?? run.status }}</span>
        </span>
        <TxFlatRadio v-if="otherTags.length" v-model="choice" size="sm">
          <TxFlatRadioItem :value="TERMINAL" :label="t.terminal" />
          <TxFlatRadioItem v-for="tag in otherTags" :key="tag" :value="tag" :label="tag" />
        </TxFlatRadio>
        <div class="output__tools">
          <TxSearchInput v-if="choice === TERMINAL" v-model="query" class="output__search" :placeholder="t.searchOutput" clearable />
          <label class="output__follow">
            <TxSwitch v-model="follow" size="small" :aria-label="t.follow" />
            <span>{{ t.follow }}</span>
          </label>
        </div>
      </div>

      <div ref="pane" class="output__pane" @scroll.passive="onScroll">
        <template v-if="choice === TERMINAL">
          <p v-if="lines.length > MAX_LINES && !query" class="output__note">
            {{ t.truncated(MAX_LINES) }}
          </p>
          <div v-for="line in shownLines" :key="line.id" class="output__line" :class="{ 'is-err': line.stream === 'stderr' }">
            <span class="output__time">{{ formatClock(line.wall) }}</span>
            <span class="output__text"><template v-for="(segment, index) in segments(display(line))" :key="index"><mark v-if="segment.hit">{{ segment.text }}</mark><template v-else>{{ segment.text }}</template></template></span>
          </div>
          <p v-if="!lines.length" class="output__note">
            {{ t.noOutput }}
          </p>
        </template>
        <template v-else>
          <article v-for="(chunk, index) in textChunks" :key="index" class="output__chunk">
            <div class="output__chunk-head">
              {{ t.step }} {{ formatCount(chunk.step) }} · {{ formatClock(chunk.wall) }}
            </div>
            <pre class="output__chunk-text">{{ chunk.text }}</pre>
          </article>
        </template>
      </div>
    </template>
  </div>
</template>

<style scoped>
.output {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
  padding: 16px 24px 24px;
}

.output__bar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 16px;
  align-items: center;
}

.output__run {
  display: inline-flex;
  gap: 8px;
  align-items: center;
  min-width: 0;
  font-weight: 600;
}

.output__run-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.output__run-status {
  font-size: 11px;
  font-weight: 500;
  color: var(--board-muted);
}

.output__run-status.is-running {
  color: var(--tx-color-success);
}

.output__run-status.is-failed {
  color: var(--tx-color-danger);
}

.output__tools {
  display: flex;
  gap: 16px;
  align-items: center;
  margin-left: auto;
}

.output__search {
  width: 220px;
}

.output__follow {
  display: inline-flex;
  gap: 8px;
  align-items: center;
  font-size: 12px;
  color: var(--tx-text-color-regular);
  cursor: pointer;
}

.output__pane {
  flex: 1;
  min-height: 320px;
  padding: 10px 0;
  overflow: auto;
  font-family: var(--board-mono);
  font-size: 12px;
  line-height: 1.6;
  color: #d4d7dd;
  background: #16171a;
  border: 1px solid var(--board-line);
  border-radius: var(--board-radius);
}

.output__line {
  display: flex;
  gap: 14px;
  padding: 0 16px;
}

.output__line:hover {
  background: rgb(255 255 255 / 4%);
}

.output__line.is-err .output__text {
  color: #ff9b8f;
}

.output__time {
  flex: none;
  color: #6b7079;
  user-select: none;
}

.output__text {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.output__text mark {
  color: #16171a;
  background: #f5b647;
  border-radius: 2px;
}

.output__note {
  margin: 0;
  padding: 4px 16px 8px;
  color: #8b9099;
}

.output__chunk {
  padding: 8px 16px;
  border-bottom: 1px solid rgb(255 255 255 / 6%);
}

.output__chunk-head {
  margin-bottom: 4px;
  color: #8b9099;
}

.output__chunk-text {
  margin: 0;
  font: inherit;
  white-space: pre-wrap;
}

.output__empty {
  margin: 64px auto;
  max-width: 420px;
}
</style>
