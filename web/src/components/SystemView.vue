<script setup lang="ts">
import { TxEmptyState } from '@talex-touch/tuffex/empty-state'
import { computed } from 'vue'
import { t } from '../i18n'
import { scalarTags, seriesOf, SYS_PREFIX, tagVersion, visibleRuns } from '../store'
import ChartCard from './ChartCard.vue'

const zh = navigator.language.toLowerCase().startsWith('zh')

// Names for the metrics tuffrl samples; anything else under sys/ keeps its tag.
const NAMES: Record<string, [zh: string, en: string]> = {
  process_cpu_percent: ['进程 CPU（%）', 'Process CPU (%)'],
  cpu_percent: ['整机 CPU（%）', 'System CPU (%)'],
  memory_percent: ['整机内存（%）', 'System memory (%)'],
  process_rss_mb: ['进程内存（MB）', 'Process memory (MB)'],
  load_1m: ['1 分钟负载', 'Load average (1 min)'],
  util_percent: ['利用率（%）', 'Utilization (%)'],
  memory_used_mb: ['显存（MB）', 'Memory used (MB)'],
  memory_total_mb: ['显存总量（MB）', 'Memory total (MB)'],
  temperature_c: ['温度（°C）', 'Temperature (°C)'],
  power_w: ['功耗（W）', 'Power (W)'],
}

function nameOf(key: string): string {
  const names = NAMES[key]
  return names ? names[zh ? 0 : 1] : key
}

const sections = computed(() => {
  const host: Array<{ tag: string, title: string }> = []
  const gpus = new Map<string, Array<{ tag: string, title: string }>>()
  for (const tag of scalarTags.value) {
    if (!tag.startsWith(SYS_PREFIX))
      continue
    void tagVersion[tag]
    if (!visibleRuns.value.some(run => (seriesOf(tag, run.id)?.points.length ?? 0) > 0))
      continue
    const rest = tag.slice(SYS_PREFIX.length)
    const gpu = /^(gpu\d+)\/(.+)$/.exec(rest)
    if (gpu) {
      // Total memory is a flat line, so the GPU section keeps to the charts that move.
      if (gpu[2] === 'memory_total_mb')
        continue
      const list = gpus.get(gpu[1]) ?? []
      list.push({ tag, title: nameOf(gpu[2]) })
      gpus.set(gpu[1], list)
    }
    else {
      host.push({ tag, title: nameOf(rest) })
    }
  }
  const list = []
  if (host.length)
    list.push({ name: zh ? 'CPU 与内存' : 'CPU and memory', tags: host })
  for (const [gpu, tags] of gpus)
    list.push({ name: gpu.toUpperCase().replace('GPU', 'GPU '), tags })
  return list
})
</script>

<template>
  <div class="system">
    <TxEmptyState v-if="!sections.length" class="system__empty" variant="no-data" :title="t.noSystem" size="small" />
    <section v-for="section in sections" :key="section.name" class="system__section">
      <h2 class="system__heading">
        {{ section.name }}
      </h2>
      <div class="system__grid">
        <ChartCard v-for="item in section.tags" :key="item.tag" :tag="item.tag" :title="item.title" system />
      </div>
    </section>
  </div>
</template>

<style scoped>
.system {
  padding: 8px 24px 32px;
}

.system__section {
  margin-top: 14px;
}

.system__heading {
  margin: 0 0 10px;
  font-size: 14px;
  font-weight: 650;
}

.system__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 14px;
}

.system__empty {
  margin: 64px auto;
  max-width: 420px;
}
</style>
