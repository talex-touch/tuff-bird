<script setup lang="ts">
import { TxEmptyState } from '@talex-touch/tuffex/empty-state'
import { computed } from 'vue'
import { t } from '../i18n'
import { scalarTags, seriesOf, SYS_PREFIX, tagVersion, ui, visibleRuns } from '../store'
import ChartCard from './ChartCard.vue'

interface Section {
  name: string
  tags: Array<{ tag: string, title: string }>
}

/** Tags of the visible runs, outside `sys/`. */
const ownTags = computed(() => scalarTags.value.filter((tag) => {
  if (tag.startsWith(SYS_PREFIX))
    return false
  void tagVersion[tag]
  return visibleRuns.value.some(run => (seriesOf(tag, run.id)?.points.length ?? 0) > 0)
}))

function matches(tag: string, query: string): boolean {
  if (!query)
    return true
  try {
    return new RegExp(query, 'i').test(tag)
  }
  catch {
    return tag.toLowerCase().includes(query.toLowerCase())
  }
}

/** Grouped by the part before the first `/`, the way TensorBoard groups them. */
const sections = computed<Section[]>(() => {
  const query = ui.tagFilter.trim()
  const byName = new Map<string, Section>()
  for (const tag of ownTags.value) {
    if (!matches(tag, query))
      continue
    const slash = tag.indexOf('/')
    const name = slash > 0 ? tag.slice(0, slash) : ''
    let section = byName.get(name)
    if (!section) {
      section = { name, tags: [] }
      byName.set(name, section)
    }
    section.tags.push({ tag, title: slash > 0 ? tag.slice(slash + 1) : tag })
  }
  // Untitled tags last, under "Other".
  return [...byName.values()].sort((a, b) => (a.name === '') === (b.name === '') ? 0 : a.name === '' ? 1 : -1)
})
</script>

<template>
  <div class="scalars">
    <TxEmptyState
      v-if="!visibleRuns.length"
      class="scalars__empty"
      variant="no-selection"
      :title="t.allHidden"
      size="small"
    />
    <TxEmptyState
      v-else-if="!sections.length"
      class="scalars__empty"
      :variant="ui.tagFilter ? 'search-empty' : 'no-data'"
      :title="ui.tagFilter ? t.noTagMatch : t.noScalars"
      size="small"
    />
    <section v-for="section in sections" :key="section.name" class="scalars__section">
      <h2 class="scalars__heading">
        {{ section.name || t.general }}
        <span class="scalars__count">{{ section.tags.length }}</span>
      </h2>
      <div class="scalars__grid">
        <ChartCard v-for="item in section.tags" :key="item.tag" :tag="item.tag" :title="item.title" />
      </div>
    </section>
  </div>
</template>

<style scoped>
.scalars {
  padding: 8px 24px 32px;
}

.scalars__section {
  margin-top: 14px;
}

.scalars__heading {
  display: flex;
  gap: 8px;
  align-items: center;
  margin: 0 0 10px;
  font-size: 14px;
  font-weight: 650;
  letter-spacing: -0.005em;
}

.scalars__count {
  padding: 0 7px;
  font-size: 11px;
  font-weight: 550;
  color: var(--board-muted);
  background: var(--tx-fill-color);
  border-radius: 999px;
}

.scalars__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
  gap: 14px;
}

.scalars__empty {
  margin: 64px auto;
  max-width: 420px;
}
</style>
