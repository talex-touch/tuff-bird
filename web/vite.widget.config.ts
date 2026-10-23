import type { Plugin } from 'vite'
import { fileURLToPath } from 'node:url'
import vue from '@vitejs/plugin-vue'
import { defineConfig, transformWithEsbuild } from 'vite'

// The chart draws in a shadow root, where :root and html match nothing, so the selectors TuffEx
// declares its variables and light theme on are moved to the chart's root element.
const scopeToChartRoot = {
  postcssPlugin: 'tuffbird-scope-to-chart-root',
  Rule(rule: { selector: string }) {
    rule.selector = rule.selector.replace(/(^|[\s,>+~(])(?::root|html)(?![\w-])/g, '$1.tb-root')
  },
}

// Library builds leave ES output's whitespace for a bundler downstream. Nothing bundles this module
// again, and every saved chart carries it, so it is minified whole.
const minifyWhole: Plugin = {
  name: 'tuffbird-minify-whole',
  async generateBundle(_options, output) {
    for (const chunk of Object.values(output)) {
      if (chunk.type === 'chunk')
        chunk.code = (await transformWithEsbuild(chunk.code, chunk.fileName, { minify: true, format: 'esm' })).code
    }
  },
}

// One ES module with Vue, the chart and their styles inside: the Python package embeds it in
// notebook outputs and saved pages, which load nothing else.
export default defineConfig({
  plugins: [vue(), minifyWhole],
  define: { 'process.env.NODE_ENV': JSON.stringify('production') },
  css: { postcss: { plugins: [scopeToChartRoot] } },
  build: {
    outDir: fileURLToPath(new URL('../src/tuffbird/charts/static', import.meta.url)),
    emptyOutDir: true,
    chunkSizeWarningLimit: 1500,
    lib: {
      entry: fileURLToPath(new URL('src/widget/index.ts', import.meta.url)),
      formats: ['es'],
      fileName: () => 'widget.js',
    },
    rollupOptions: { output: { inlineDynamicImports: true } },
  },
})
