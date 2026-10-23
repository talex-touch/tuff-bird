<script setup lang="ts">
import type { LearningCurveRun } from '@talex-touch/tuffex/charts/src/learning-curve'
import { TxChartLegendItem } from '@talex-touch/tuffex/charts/src/chart-legend'
import { TxLearningCurve } from '@talex-touch/tuffex/charts/src/learning-curve'
import { TxSlider } from '@talex-touch/tuffex/slider'
import { computed, ref } from 'vue'
import { formatCount, formatValue } from '../format'
import { t } from './i18n'
import type { Chart } from './spec'

// Styles live in widget.css: the chart draws inside a shadow root, which only sees the CSS put there.
const props = defineProps<{
  chart: Chart
  /** Bumped when points are appended to the chart's series in place. */
  version: number
  /**
   * The kernel has saved the chart in the output that showed it. A view still drawing was opened
   * after that output, in a page reloaded since, and its output stays the widget.
   */
  saved?: boolean
}>()

const hidden = ref(new Set<string>())
/** The curve under the pointer in the legend, emphasized in every panel. */
const highlighted = ref<string | null>(null)
/** The chart's smoothing to start with; the reader can change it, as on the board. */
const smoothing = ref(props.chart.smoothing)

/** Each curve once, in the order the panels first draw them. */
const legend = computed(() => {
  const items = new Map<string, { key: string, name: string, color: string, runs: number }>()
  for (const panel of props.chart.panels) {
    for (const curve of panel.curves) {
      const item = items.get(curve.key)
      if (!item)
        items.set(curve.key, { key: curve.key, name: curve.name, color: curve.color, runs: curve.runs.length })
      else
        item.runs = Math.max(item.runs, curve.runs.length)
    }
  }
  return [...items.values()]
})

/** Each curve as one run of TxLearningCurve: a single run's points, or a group's runs as seeds. */
const panels = computed(() => {
  void props.version
  return props.chart.panels.map(panel => ({
    tag: panel.tag,
    runs: panel.curves
      .filter(curve => !hidden.value.has(curve.key))
      .map((curve): LearningCurveRun => curve.runs.length === 1
        ? { name: curve.name, data: curve.runs[0].points, color: curve.color }
        : { name: curve.name, seeds: curve.runs.map(run => run.points), color: curve.color }),
  }))
})

// A hidden curve has nothing to emphasize; naming it would only dim the others.
const highlightedName = computed(() => {
  const key = highlighted.value
  return key && !hidden.value.has(key) ? legend.value.find(item => item.key === key)?.name ?? null : null
})

function toggle(key: string): void {
  const next = new Set(hidden.value)
  if (!next.delete(key))
    next.add(key)
  hidden.value = next
}
</script>

<template>
  <div class="tb-chart">
    <header class="tb-chart__head">
      <h3 v-if="chart.title" class="tb-chart__title">
        {{ chart.title }}
      </h3>
      <div v-if="legend.length" class="tb-chart__legend">
        <TxChartLegendItem
          v-for="item in legend"
          :key="item.key"
          :name="item.name"
          :color="item.color"
          :value="item.runs > 1 ? `n=${item.runs}` : ''"
          :inactive="hidden.has(item.key)"
          :aria-pressed="!hidden.has(item.key)"
          :title="hidden.has(item.key) ? t.show : t.hide"
          @click="toggle(item.key)"
          @mouseenter="highlighted = item.key"
          @mouseleave="highlighted = null"
          @focus="highlighted = item.key"
          @blur="highlighted = null"
        />
      </div>
      <label class="tb-chart__smoothing">
        <span>{{ t.smoothing }}</span>
        <TxSlider v-model="smoothing" class="tb-chart__slider" :min="0" :max="0.99" :step="0.01" :aria-label="t.smoothing" />
        <span class="tb-chart__value">{{ smoothing.toFixed(2) }}</span>
      </label>
    </header>
    <p v-if="saved" class="tb-chart__notice" role="status">
      {{ t.notSaved }}
    </p>
    <div class="tb-chart__panels">
      <article v-for="panel in panels" :key="panel.tag" class="tb-chart__panel">
        <h4 class="tb-chart__tag" :title="panel.tag">
          {{ panel.tag }}
        </h4>
        <TxLearningCurve
          :runs="panel.runs"
          :smoothing="smoothing"
          :show-raw="chart.showRaw"
          :show-band="true"
          :x-type="chart.logX ? 'log' : 'linear'"
          :highlighted-run="highlightedName"
          :height="chart.height"
          :step-format="formatCount"
          :tooltip-value-format="formatValue"
          :aria-description="panel.tag"
        />
      </article>
    </div>
  </div>
</template>
