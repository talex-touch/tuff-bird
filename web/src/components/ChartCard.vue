<script setup lang="ts">
import type { LearningCurveRun } from '@talex-touch/tuffex/charts/src/learning-curve'
import { TxLearningCurve } from '@talex-touch/tuffex/charts/src/learning-curve'
import { TxSkeleton } from '@talex-touch/tuffex/skeleton'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { chartCode, copyText } from '../chart-code'
import { formatCount, formatDuration, formatValue } from '../format'
import { t } from '../i18n'
import { colorOf, groups, prefs, runLabels, seriesKeyOf, seriesOf, tagVersion, ui, visibleRuns } from '../store'

const props = defineProps<{
  tag: string
  title: string
  /** System metrics: x is seconds since the run started, and the values are not smoothed. */
  system?: boolean
}>()

const expanded = ref(false)
const height = computed(() => (expanded.value ? 380 : 220))

/** What the last copy did, shown on the button for a moment. */
const copied = ref<'done' | 'failed' | null>(null)
let copiedTimer: number | undefined
const copyLabel = computed(() => (copied.value === 'done' ? t.copied : copied.value === 'failed' ? t.copyFailed : t.copyCode))

async function copyCode(): Promise<void> {
  copied.value = (await copyText(chartCode(props.tag))) ? 'done' : 'failed'
  window.clearTimeout(copiedTimer)
  copiedTimer = window.setTimeout(() => {
    copied.value = null
  }, 1600)
}

const groupLabels = computed(() => new Map(groups.value.map(group => [`group:${group.key}`, group.label])))

/** Each visible run as one curve, or each group as one curve with a band across its runs. */
const curves = computed(() => {
  void tagVersion[props.tag]
  const list: LearningCurveRun[] = []
  const merged = new Map<string, LearningCurveRun & { seeds: Array<Array<[number, number]>> }>()
  const names = new Map<string, string>()
  for (const run of visibleRuns.value) {
    const series = seriesOf(props.tag, run.id)
    if (!series?.points.length)
      continue
    const key = seriesKeyOf(run)
    if (key === run.id) {
      const name = runLabels.value.get(run.id) ?? run.id
      names.set(key, name)
      list.push({ name, data: series.points, color: colorOf(key) })
      continue
    }
    let entry = merged.get(key)
    if (!entry) {
      const name = groupLabels.value.get(key) ?? key
      names.set(key, name)
      entry = { name, seeds: [], color: colorOf(key) }
      merged.set(key, entry)
      list.push(entry)
    }
    entry.seeds.push(series.points)
  }
  return { list, names }
})

const highlighted = computed(() => (ui.highlighted ? curves.value.names.get(ui.highlighted) ?? null : null))

const labels = computed(() => ({
  step: props.system ? (value: string) => value : t.stepAt,
}))

function secondsTick(seconds: number): string {
  return seconds < 120 ? `${Math.round(seconds)}s` : `${Number((seconds / 60).toFixed(1))}m`
}

const root = ref<HTMLElement>()
// Charts far below the fold are drawn once they come near, so a board with hundreds of tags
// opens as fast as one with ten.
const seen = ref(false)
let observer: IntersectionObserver | null = null

onMounted(() => {
  const element = root.value
  if (!element)
    return
  observer = new IntersectionObserver((entries) => {
    if (entries.some(entry => entry.isIntersecting)) {
      seen.value = true
      observer?.disconnect()
    }
  }, { root: element.closest('.board__main'), rootMargin: '600px 0px' })
  observer.observe(element)
})

onBeforeUnmount(() => {
  observer?.disconnect()
  window.clearTimeout(copiedTimer)
})
</script>

<template>
  <article ref="root" class="card" :class="{ 'is-expanded': expanded }">
    <header class="card__head">
      <h3 class="card__title" :title="tag">
        {{ title }}
      </h3>
      <span v-if="title !== tag" class="card__tag mono">{{ tag }}</span>
      <div class="card__actions">
        <!-- System metrics are drawn against time, which tuffbird's plot() and chart() do not do. -->
        <button
          v-if="!system"
          class="card__action"
          :class="{ 'is-shown': copied }"
          type="button"
          :title="copyLabel"
          :aria-label="copyLabel"
          @click="copyCode"
        >
          <svg viewBox="0 0 16 16" aria-hidden="true">
            <path v-if="copied === 'done'" d="M3 8.5 6.5 12 13 4.5" />
            <path v-else-if="copied === 'failed'" d="M4 4l8 8M12 4l-8 8" />
            <path v-else d="M5.5 4.5 2 8l3.5 3.5M10.5 4.5 14 8l-3.5 3.5" />
          </svg>
        </button>
        <button
          class="card__action"
          :class="{ 'is-shown': expanded }"
          type="button"
          :aria-pressed="expanded"
          :aria-label="expanded ? 'collapse' : 'expand'"
          @click="expanded = !expanded"
        >
          <svg viewBox="0 0 16 16" aria-hidden="true">
            <path v-if="expanded" d="M6 2v4H2M10 14v-4h4M6 6 2 2M10 10l4 4" />
            <path v-else d="M10 2h4v4M6 14H2v-4M14 2 9.5 6.5M2 14l4.5-4.5" />
          </svg>
        </button>
      </div>
    </header>
    <TxLearningCurve
      v-if="seen"
      :runs="curves.list"
      :smoothing="system ? 0 : prefs.smoothing"
      :show-raw="!system && prefs.showRaw"
      :show-band="true"
      :x-type="!system && prefs.logX ? 'log' : 'linear'"
      :highlighted-run="highlighted"
      :height="height"
      :labels="labels"
      :step-format="system ? formatDuration : formatCount"
      :x-axis-tick-format="system ? secondsTick : undefined"
      :tooltip-value-format="formatValue"
      :aria-description="tag"
    />
    <TxSkeleton v-else :height="`${height}px`" radius="8px" />
  </article>
</template>

<style scoped>
.card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
  padding: 12px 14px 10px;
  background: var(--board-surface);
  border: 1px solid var(--board-line);
  border-radius: var(--board-radius);
}

.card.is-expanded {
  grid-column: 1 / -1;
}

.card__head {
  display: flex;
  gap: 8px;
  align-items: baseline;
  min-width: 0;
}

.card__title {
  margin: 0;
  overflow: hidden;
  font-size: 13px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card__tag {
  overflow: hidden;
  min-width: 0;
  font-size: 11px;
  color: var(--board-muted);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card__actions {
  display: flex;
  flex: none;
  gap: 2px;
  margin: -4px -6px 0 auto;
}

.card__action {
  display: grid;
  flex: none;
  place-items: center;
  width: 24px;
  height: 24px;
  padding: 0;
  color: var(--board-muted);
  cursor: pointer;
  background: none;
  border: 0;
  border-radius: 6px;
  opacity: 0;
  transition: opacity 0.15s ease, background-color 0.15s ease;
}

.card:hover .card__action,
.card__action:focus-visible,
.card__action.is-shown {
  opacity: 1;
}

.card__action:hover {
  color: var(--tx-text-color-primary);
  background: var(--tx-fill-color-light);
}

.card__action svg {
  width: 14px;
  height: 14px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.5;
  stroke-linecap: round;
  stroke-linejoin: round;
}
</style>
