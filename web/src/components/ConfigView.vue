<script setup lang="ts">
import type { RunMeta } from '../api'
import { TxEmptyState } from '@talex-touch/tuffex/empty-state'
import { TxSwitch } from '@talex-touch/tuffex/switch'
import { computed, ref } from 'vue'
import { formatDateTime, formatDuration, naturalCompare } from '../format'
import { t } from '../i18n'
import { colorOf, now, runLabels, ui, visibleRuns } from '../store'

const onlyDiff = ref(false)

function show(value: unknown): string {
  if (value === null || value === undefined)
    return '—'
  if (typeof value === 'string')
    return value
  return JSON.stringify(value)
}

const keys = computed(() => {
  const all = new Set<string>()
  for (const run of visibleRuns.value) {
    for (const key of Object.keys(run.hparams))
      all.add(key)
  }
  return [...all].sort(naturalCompare)
})

/** Keys whose value is not the same in every visible run (a missing key counts as a value). */
const differing = computed(() => {
  const set = new Set<string>()
  if (visibleRuns.value.length < 2)
    return set
  for (const key of keys.value) {
    const first = show(visibleRuns.value[0].hparams[key])
    if (visibleRuns.value.some(run => show(run.hparams[key]) !== first))
      set.add(key)
  }
  return set
})

const rows = computed(() => (onlyDiff.value ? keys.value.filter(key => differing.value.has(key)) : keys.value))

function duration(run: RunMeta): string {
  if (!run.startTime)
    return '—'
  const end = run.status === 'running' ? now.value : (run.endTime ?? run.lastWall ?? run.lastWrite)
  return formatDuration(end - run.startTime)
}
</script>

<template>
  <div class="config">
    <TxEmptyState v-if="!visibleRuns.length" class="config__empty" variant="no-selection" :title="t.allHidden" size="small" />
    <template v-else>
      <div class="config__bar">
        <label class="config__toggle">
          <TxSwitch v-model="onlyDiff" size="small" :aria-label="t.onlyDiff" />
          <span>{{ t.onlyDiff }}</span>
          <span class="config__diff-count">{{ differing.size }}</span>
        </label>
      </div>
      <div class="config__scroll">
        <table class="config__table">
          <thead>
            <tr>
              <th class="config__key">
                {{ t.key }}
              </th>
              <th
                v-for="run in visibleRuns"
                :key="run.id"
                :class="{ 'is-highlighted': ui.highlighted === run.id }"
                :title="run.id"
              >
                <span class="config__run">
                  <span class="swatch" :style="{ '--swatch': colorOf(run.id) }" />
                  {{ runLabels.get(run.id) ?? run.name }}
                </span>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr class="config__meta">
              <td class="config__key">
                {{ t.statusLabel }}
              </td>
              <td v-for="run in visibleRuns" :key="run.id">
                <span class="config__status" :class="`is-${run.status}`">{{ t.status[run.status] ?? run.status }}</span>
              </td>
            </tr>
            <tr class="config__meta">
              <td class="config__key">
                {{ t.started }}
              </td>
              <td v-for="run in visibleRuns" :key="run.id" class="mono">
                {{ run.startTime ? formatDateTime(run.startTime) : '—' }}
              </td>
            </tr>
            <tr class="config__meta is-last">
              <td class="config__key">
                {{ t.duration }}
              </td>
              <td v-for="run in visibleRuns" :key="run.id" class="mono">
                {{ duration(run) }}
              </td>
            </tr>
            <tr v-for="key in rows" :key="key" :class="{ 'is-diff': differing.has(key) }">
              <td class="config__key mono" :title="key">
                {{ key }}
              </td>
              <td v-for="run in visibleRuns" :key="run.id" class="mono" :class="{ 'is-missing': !(key in run.hparams) }">
                {{ show(run.hparams[key]) }}
              </td>
            </tr>
          </tbody>
        </table>
        <p v-if="!keys.length" class="config__none muted">
          {{ t.noConfig }}
        </p>
      </div>
    </template>
  </div>
</template>

<style scoped>
.config {
  padding: 16px 24px 32px;
}

.config__bar {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
}

.config__toggle {
  display: inline-flex;
  gap: 8px;
  align-items: center;
  font-size: 12px;
  color: var(--tx-text-color-regular);
  cursor: pointer;
}

.config__diff-count {
  padding: 0 7px;
  font-size: 11px;
  color: var(--board-muted);
  background: var(--tx-fill-color);
  border-radius: 999px;
}

.config__scroll {
  overflow: auto;
  background: var(--board-surface);
  border: 1px solid var(--board-line);
  border-radius: var(--board-radius);
}

.config__table {
  width: max-content;
  min-width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 12px;
}

.config__table th,
.config__table td {
  max-width: 280px;
  padding: 7px 14px;
  overflow: hidden;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
  border-bottom: 1px solid var(--board-line);
}

.config__table th {
  position: sticky;
  top: 0;
  z-index: 1;
  font-weight: 600;
  background: var(--tx-fill-color-light);
}

.config__table th.is-highlighted {
  background: color-mix(in srgb, var(--tx-color-primary) 10%, var(--tx-fill-color-light));
}

.config__key {
  position: sticky;
  left: 0;
  z-index: 2;
  min-width: 200px;
  color: var(--tx-text-color-regular);
  background: var(--board-surface);
  box-shadow: inset -1px 0 0 var(--board-line);
}

.config__table th.config__key {
  z-index: 3;
  background: var(--tx-fill-color-light);
}

.config__run {
  display: inline-flex;
  gap: 7px;
  align-items: center;
}

.config__meta td {
  color: var(--tx-text-color-regular);
}

.config__meta.is-last td {
  border-bottom: 1px solid var(--tx-border-color-light);
}

tr.is-diff td {
  font-weight: 600;
  background: color-mix(in srgb, var(--tx-color-warning) 8%, transparent);
}

tr.is-diff td.config__key {
  background: color-mix(in srgb, var(--tx-color-warning) 8%, var(--board-surface));
  box-shadow: inset 3px 0 0 var(--tx-color-warning), inset -1px 0 0 var(--board-line);
}

td.is-missing {
  color: var(--board-muted);
}

tbody tr:last-child td {
  border-bottom: 0;
}

.config__status.is-running {
  color: var(--tx-color-success);
}

.config__status.is-failed {
  color: var(--tx-color-danger);
}

.config__none {
  margin: 0;
  padding: 16px;
}

.config__empty {
  margin: 64px auto;
  max-width: 420px;
}
</style>
