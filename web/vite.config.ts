import { fileURLToPath } from 'node:url'
import vue from '@vitejs/plugin-vue'
import tuffexOnDemandStyle from '@talex-touch/tuffex/vite'
import { defineConfig } from 'vite'

// `pnpm dev` talks to a board started with `tuff-rl board <logdir>` on the default port.
const board = process.env.TUFFRL_BOARD_URL ?? 'http://127.0.0.1:6066'

export default defineConfig({
  base: './',
  plugins: [vue(), tuffexOnDemandStyle()],
  build: {
    // The Python package serves the board from here and ships it in the wheel.
    outDir: fileURLToPath(new URL('../src/tuffrl/board/static', import.meta.url)),
    emptyOutDir: true,
    chunkSizeWarningLimit: 1500,
  },
  server: {
    proxy: { '/api': { target: board, changeOrigin: true } },
  },
})
