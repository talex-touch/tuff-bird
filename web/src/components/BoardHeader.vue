<script setup lang="ts">
import { computed } from 'vue'
import { t } from '../i18n'
import { board, runningCount, runs } from '../store'

const connection = computed(() => board.connection)
</script>

<template>
  <header class="header">
    <div class="header__brand">
      <svg class="header__mark" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M3 17.5 8.5 11l4 3.5L21 5" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" />
        <circle cx="21" cy="5" r="2" fill="currentColor" />
      </svg>
      <span class="header__name">tuff-rl</span>
    </div>
    <span class="header__logdir mono" :title="board.logdir"><bdi>{{ board.logdir }}</bdi></span>
    <div class="header__status">
      <span v-if="runs.length" class="header__count">{{ t.runCount(runningCount, runs.length) }}</span>
      <span class="header__live" :class="`is-${connection}`">
        <span class="header__dot" />
        {{ t.connection[connection] }}
      </span>
    </div>
  </header>
</template>

<style scoped>
.header {
  display: flex;
  flex: none;
  gap: 16px;
  align-items: center;
  height: var(--board-header);
  padding: 0 20px;
  background: var(--board-surface);
  border-bottom: 1px solid var(--board-line);
}

.header__brand {
  display: flex;
  flex: none;
  gap: 8px;
  align-items: center;
}

.header__mark {
  width: 22px;
  height: 22px;
  padding: 3px;
  color: #fff;
  background: linear-gradient(135deg, #4290f0, #8d58ee);
  border-radius: 7px;
}

.header__name {
  font-size: 15px;
  font-weight: 650;
  letter-spacing: -0.01em;
}

.header__logdir {
  overflow: hidden;
  min-width: 0;
  padding: 3px 8px;
  font-size: 12px;
  color: var(--board-muted);
  text-overflow: ellipsis;
  white-space: nowrap;
  direction: rtl; /* a long path loses its start, not the directory it names */
  background: var(--tx-fill-color-light);
  border-radius: 6px;
}

.header__status {
  display: flex;
  flex: none;
  gap: 14px;
  align-items: center;
  margin-left: auto;
}

.header__count {
  color: var(--board-muted);
}

.header__live {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  padding: 3px 10px 3px 8px;
  font-size: 12px;
  font-weight: 550;
  border-radius: 999px;
  background: var(--tx-fill-color-light);
}

.header__dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--board-muted);
}

.header__live.is-live {
  color: var(--tx-color-success);
  background: color-mix(in srgb, var(--tx-color-success) 12%, transparent);
}

.header__live.is-live .header__dot {
  background: var(--tx-color-success);
  animation: header-pulse 2s ease-out infinite;
}

.header__live.is-reconnecting,
.header__live.is-loading {
  color: var(--tx-color-warning);
  background: color-mix(in srgb, var(--tx-color-warning) 12%, transparent);
}

.header__live.is-reconnecting .header__dot,
.header__live.is-loading .header__dot {
  background: var(--tx-color-warning);
}

.header__live.is-error {
  color: var(--tx-color-danger);
  background: color-mix(in srgb, var(--tx-color-danger) 12%, transparent);
}

.header__live.is-error .header__dot {
  background: var(--tx-color-danger);
}

@keyframes header-pulse {
  0% {
    box-shadow: 0 0 0 0 color-mix(in srgb, var(--tx-color-success) 55%, transparent);
  }

  100% {
    box-shadow: 0 0 0 7px transparent;
  }
}

@media (prefers-reduced-motion: reduce) {
  .header__live.is-live .header__dot {
    animation: none;
  }
}
</style>
