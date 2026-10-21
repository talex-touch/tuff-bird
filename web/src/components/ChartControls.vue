<script setup lang="ts">
import { TxSearchInput } from '@talex-touch/tuffex/search-input'
import { TxSlider } from '@talex-touch/tuffex/slider'
import { TxSwitch } from '@talex-touch/tuffex/switch'
import { t } from '../i18n'
import { prefs, ui } from '../store'

defineProps<{ system?: boolean }>()
</script>

<template>
  <div class="controls">
    <TxSearchInput v-if="!system" v-model="ui.tagFilter" class="controls__filter" :placeholder="t.filterTags" clearable />
    <label v-if="!system" class="controls__item controls__smoothing">
      <span>{{ t.smoothing }}</span>
      <TxSlider v-model="prefs.smoothing" class="controls__slider" :min="0" :max="0.99" :step="0.01" :aria-label="t.smoothing" />
      <span class="controls__value mono">{{ prefs.smoothing.toFixed(2) }}</span>
    </label>
    <label v-if="!system" class="controls__item">
      <TxSwitch v-model="prefs.showRaw" size="small" :aria-label="t.raw" />
      <span>{{ t.raw }}</span>
    </label>
    <label class="controls__item">
      <TxSwitch v-model="prefs.mergeGroups" size="small" :aria-label="t.mergeSeeds" />
      <span>{{ t.mergeSeeds }}</span>
    </label>
    <label v-if="!system" class="controls__item">
      <TxSwitch v-model="prefs.logX" size="small" :aria-label="t.logX" />
      <span>{{ t.logX }}</span>
    </label>
  </div>
</template>

<style scoped>
.controls {
  display: flex;
  flex: 1;
  flex-wrap: wrap;
  gap: 10px 18px;
  align-items: center;
  justify-content: flex-end;
  min-width: 0;
}

.controls__filter {
  width: 220px;
  margin-right: auto;
}

.controls__item {
  display: inline-flex;
  gap: 8px;
  align-items: center;
  font-size: 12px;
  color: var(--tx-text-color-regular);
  white-space: nowrap;
  cursor: pointer;
  user-select: none;
}

.controls__smoothing {
  cursor: default;
}

.controls__slider {
  width: 120px;
}

.controls__value {
  width: 30px;
  font-size: 12px;
  color: var(--board-muted);
}
</style>
