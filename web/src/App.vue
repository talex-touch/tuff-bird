<script setup lang="ts">
import { TxEmptyState } from '@talex-touch/tuffex/empty-state'
import { TxFlatRadio, TxFlatRadioItem } from '@talex-touch/tuffex/flat-radio'
import { TxSkeleton } from '@talex-touch/tuffex/skeleton'
import { onMounted } from 'vue'
import BoardHeader from './components/BoardHeader.vue'
import ChartControls from './components/ChartControls.vue'
import ConfigView from './components/ConfigView.vue'
import OutputView from './components/OutputView.vue'
import RunList from './components/RunList.vue'
import ScalarsView from './components/ScalarsView.vue'
import SystemView from './components/SystemView.vue'
import { t } from './i18n'
import { board, connect, prefs, runs } from './store'

const VIEWS = ['scalars', 'config', 'output', 'system'] as const

onMounted(connect)
</script>

<template>
  <div class="board">
    <BoardHeader />
    <div class="board__body">
      <RunList class="board__runs" />
      <main class="board__main">
        <div class="board__toolbar">
          <TxFlatRadio v-model="prefs.view" size="sm" class="board__views">
            <TxFlatRadioItem v-for="view in VIEWS" :key="view" :value="view" :label="t.views[view]" />
          </TxFlatRadio>
          <ChartControls v-if="prefs.view === 'scalars' || prefs.view === 'system'" :system="prefs.view === 'system'" />
        </div>

        <div v-if="board.connection === 'loading'" class="board__placeholder">
          <div v-for="index in 6" :key="index" class="board__placeholder-card">
            <TxSkeleton width="40%" height="14px" />
            <TxSkeleton height="190px" radius="8px" />
          </div>
        </div>
        <TxEmptyState
          v-else-if="!runs.length"
          class="board__empty"
          :variant="board.connection === 'error' ? 'offline' : 'empty'"
          :title="board.connection === 'error' ? t.boardDownTitle : t.noRunsTitle"
          :description="board.connection === 'error' ? t.boardDownBody : t.noRunsBody"
        />
        <ScalarsView v-else-if="prefs.view === 'scalars'" />
        <ConfigView v-else-if="prefs.view === 'config'" />
        <OutputView v-else-if="prefs.view === 'output'" />
        <SystemView v-else />
      </main>
    </div>
  </div>
</template>

<style scoped>
.board {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.board__body {
  display: flex;
  flex: 1;
  min-height: 0;
}

.board__runs {
  flex: none;
  width: var(--board-sidebar);
}

.board__main {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  overflow: auto;
}

.board__toolbar {
  position: sticky;
  top: 0;
  z-index: 5;
  display: flex;
  flex-wrap: wrap;
  gap: 12px 20px;
  align-items: center;
  padding: 12px 24px;
  background: color-mix(in srgb, var(--board-surface) 88%, transparent);
  backdrop-filter: saturate(1.4) blur(14px);
  border-bottom: 1px solid var(--board-line);
}

.board__views {
  flex: none;
}

.board__placeholder {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
  gap: 16px;
  padding: 20px 24px;
}

.board__placeholder-card {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 16px;
  background: var(--board-surface);
  border: 1px solid var(--board-line);
  border-radius: var(--board-radius);
}

.board__empty {
  margin: auto;
  max-width: 460px;
  padding: 48px 24px;
}

@media (max-width: 860px) {
  .board__body {
    flex-direction: column;
  }

  .board__runs {
    width: auto;
    max-height: 40vh;
  }
}
</style>
