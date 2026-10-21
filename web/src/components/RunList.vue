<script setup lang="ts">
import type { RunMeta } from '../api'
import type { RunGroup } from '../store'
import { TxCheckbox } from '@talex-touch/tuffex/checkbox'
import { TxSearchInput } from '@talex-touch/tuffex/search-input'
import { computed } from 'vue'
import { formatCount, formatDuration } from '../format'
import { t } from '../i18n'
import { colorOf, groups, lastStep, now, prefs, runLabels, runs, seriesKeyOf, ui } from '../store'

const shownGroups = computed<RunGroup[]>(() => {
  const query = ui.runFilter.trim().toLowerCase()
  if (!query)
    return groups.value
  return groups.value
    .map(group => ({ ...group, runs: group.runs.filter(run => (runLabels.value.get(run.id) ?? run.id).toLowerCase().includes(query)) }))
    .filter(group => group.runs.length > 0)
})

const hiddenCount = computed(() => runs.value.filter(run => ui.hidden.has(run.id)).length)

function setVisible(ids: string[], visible: boolean): void {
  for (const id of ids) {
    if (visible)
      ui.hidden.delete(id)
    else
      ui.hidden.add(id)
  }
}

function groupState(group: RunGroup): { checked: boolean, mixed: boolean } {
  const shown = group.runs.filter(run => !ui.hidden.has(run.id)).length
  return { checked: shown > 0, mixed: shown > 0 && shown < group.runs.length }
}

function elapsed(run: RunMeta): string {
  if (!run.startTime)
    return ''
  const end = run.status === 'running' ? now.value : (run.endTime ?? run.lastWall ?? run.lastWrite)
  return formatDuration(end - run.startTime)
}

function focus(run: RunMeta): void {
  ui.focused = run.id
}

const statusOrder: Record<string, number> = { running: 0, idle: 1, failed: 2, stopped: 3, finished: 4 }

function groupStatus(group: RunGroup): string {
  return group.runs.map(run => run.status).sort((a, b) => (statusOrder[a] ?? 9) - (statusOrder[b] ?? 9))[0] ?? 'idle'
}
</script>

<template>
  <aside class="runs">
    <div class="runs__head">
      <div class="runs__title">
        <span>{{ t.runs }}</span>
        <span class="runs__total">{{ runs.length }}</span>
        <button v-if="hiddenCount" class="runs__show-all" type="button" @click="ui.hidden.clear()">
          {{ t.showAll }}
        </button>
      </div>
      <TxSearchInput v-model="ui.runFilter" :placeholder="t.filterRuns" clearable />
    </div>

    <div class="runs__list">
      <section v-for="group in shownGroups" :key="group.key" class="runs__group">
        <div
          v-if="group.key"
          class="runs__group-head"
          @pointerenter="ui.highlighted = prefs.mergeGroups ? `group:${group.key}` : null"
          @pointerleave="ui.highlighted = null"
        >
          <TxCheckbox
            :model-value="groupState(group).checked"
            :indeterminate="groupState(group).mixed"
            :aria-label="group.label"
            @update:model-value="(value: boolean) => setVisible(group.runs.map(run => run.id), value)"
          />
          <span v-if="prefs.mergeGroups" class="swatch" :style="{ '--swatch': colorOf(`group:${group.key}`) }" />
          <span class="runs__group-name" :title="group.key">{{ group.label }}</span>
          <span class="runs__group-count">{{ group.runs.length }}</span>
          <span v-if="prefs.mergeGroups" class="runs__status" :class="`is-${groupStatus(group)}`" :title="t.status[groupStatus(group)]" />
        </div>

        <div
          v-for="run in group.runs"
          :key="run.id"
          class="runs__item"
          :class="{ 'is-hidden': ui.hidden.has(run.id), 'is-focused': ui.focused === run.id, 'is-nested': !!group.key }"
          @pointerenter="ui.highlighted = seriesKeyOf(run)"
          @pointerleave="ui.highlighted = null"
          @click="focus(run)"
        >
          <TxCheckbox
            :model-value="!ui.hidden.has(run.id)"
            :aria-label="run.id"
            @click.stop
            @update:model-value="(value: boolean) => setVisible([run.id], value)"
          />
          <span class="swatch" :class="{ 'is-muted': prefs.mergeGroups && group.key }" :style="{ '--swatch': colorOf(run.id) }" />
          <div class="runs__text">
            <span class="runs__name" :title="run.id">{{ group.key ? run.name : (runLabels.get(run.id) ?? run.name) }}</span>
            <span class="runs__meta mono">
              <template v-if="lastStep[run.id] !== undefined">{{ t.step }} {{ formatCount(lastStep[run.id]) }}</template>
              <template v-if="lastStep[run.id] !== undefined && run.startTime"> · </template>
              {{ elapsed(run) }}
            </span>
          </div>
          <span class="runs__status-label" :class="`is-${run.status}`">
            <span class="runs__status" :class="`is-${run.status}`" />
            {{ t.status[run.status] ?? run.status }}
          </span>
        </div>
      </section>
    </div>
  </aside>
</template>

<style scoped>
.runs {
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: var(--board-surface);
  border-right: 1px solid var(--board-line);
}

.runs__head {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px 14px 10px;
}

.runs__title {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 12px;
  font-weight: 650;
  letter-spacing: 0.02em;
  color: var(--tx-text-color-regular);
  text-transform: uppercase;
}

.runs__total {
  padding: 0 6px;
  font-weight: 550;
  color: var(--board-muted);
  background: var(--tx-fill-color-light);
  border-radius: 999px;
}

.runs__show-all {
  margin-left: auto;
  padding: 0;
  font-size: 12px;
  font-weight: 500;
  color: var(--tx-color-primary);
  text-transform: none;
  letter-spacing: 0;
  cursor: pointer;
  background: none;
  border: 0;
}

.runs__list {
  flex: 1;
  min-height: 0;
  padding: 0 8px 16px;
  overflow: auto;
}

.runs__group + .runs__group {
  margin-top: 6px;
}

.runs__group-head {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 8px 8px 4px;
  font-size: 12px;
  font-weight: 600;
  color: var(--tx-text-color-regular);
}

.runs__group-name {
  overflow: hidden;
  min-width: 0;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.runs__group-count {
  font-weight: 500;
  color: var(--board-muted);
}

.runs__item {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 6px 8px;
  cursor: pointer;
  border-radius: 8px;
  transition: background-color 0.15s ease;
}

.runs__item.is-nested {
  padding-left: 22px;
}

.runs__item:hover {
  background: var(--tx-fill-color-light);
}

.runs__item.is-focused {
  background: color-mix(in srgb, var(--tx-color-primary) 9%, transparent);
}

.runs__item.is-hidden .runs__text,
.runs__item.is-hidden .swatch {
  opacity: 0.4;
}

.swatch.is-muted {
  opacity: 0.35;
}

.runs__text {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
}

.runs__name {
  overflow: hidden;
  font-weight: 550;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.runs__meta {
  overflow: hidden;
  font-size: 11px;
  color: var(--board-muted);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.runs__status-label {
  display: inline-flex;
  flex: none;
  gap: 5px;
  align-items: center;
  font-size: 11px;
  color: var(--board-muted);
}

.runs__status {
  flex: none;
  width: 6px;
  height: 6px;
  margin-left: auto;
  border-radius: 50%;
  background: var(--board-muted);
}

.runs__status.is-running {
  background: var(--tx-color-success);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--tx-color-success) 20%, transparent);
}

.runs__status-label.is-running {
  color: var(--tx-color-success);
}

.runs__status.is-idle {
  background: var(--tx-color-warning);
}

.runs__status.is-failed {
  background: var(--tx-color-danger);
}

.runs__status-label.is-failed {
  color: var(--tx-color-danger);
}

.runs__status.is-finished {
  background: var(--tx-color-primary);
}
</style>
