/**
 * The board's chart on its own, as one ES module: the Jupyter widget that `tuffbird.charts.live` shows
 * while runs write (anywidget's `initialize` and `render`), and `mount` for the saved chart, which
 * opens without a kernel.
 *
 * Each chart draws in a shadow root with TuffEx's styles inside it, so a notebook's or a page's CSS
 * cannot reach it and its CSS cannot reach them.
 */
import type { Ref, ShallowRef } from 'vue'
import type { Chart, ChartSpec } from './spec'
import baseCss from '@talex-touch/tuffex/base.css?inline'
import chartsCss from '@talex-touch/tuffex/charts/style.css?inline'
import sliderCss from '@talex-touch/tuffex/slider/style.css?inline'
import { createApp, h, ref, shallowRef } from 'vue'
import ChartView from './ChartView.vue'
import { appendPoints, isAppend, readSpec } from './spec'
import widgetCss from './widget.css?inline'

// TxSlider draws its glass surface only with thumbVariant 'glass', which the chart does not use.
const STYLES = [baseCss, chartsCss, sliderCss, widgetCss].join('\n')

interface Store {
  chart: ShallowRef<Chart>
  /** Bumped when points land in the chart's series. */
  version: Ref<number>
  /** The widget's `saved`: the kernel has put the saved chart in the output that showed the widget. */
  saved: Ref<boolean>
}

function createStore(spec: ChartSpec, saved = false): Store {
  return { chart: shallowRef(readSpec(spec)), version: ref(0), saved: ref(saved) }
}

/** Whether the page around the chart is dark: JupyterLab's theme, VS Code's, the page's class, or the system's. */
function isDark(): boolean {
  const body = document.body?.dataset ?? {}
  if (body.jpThemeLight === 'true' || body.jpThemeLight === 'false')
    return body.jpThemeLight === 'false'
  if (body.vscodeThemeKind)
    return body.vscodeThemeKind === 'vscode-dark' || body.vscodeThemeKind === 'vscode-high-contrast'
  const html = document.documentElement
  const theme = html.dataset.theme ?? html.getAttribute('theme')
  if (html.classList.contains('dark') || theme === 'dark')
    return true
  if (html.classList.contains('light') || theme === 'light')
    return false
  return matchMedia('(prefers-color-scheme: dark)').matches
}

/** Draws the chart in `container`; returns what removes it. */
function draw(container: HTMLElement, store: Store): () => void {
  const host = document.createElement('div')
  host.className = 'tuffbird-chart__host'
  // JupyterLab binds the arrow keys, Enter and letters to notebook commands, which would take the keys
  // pressed on the chart's slider and legend. Lumino looks no further than an element with this mark.
  host.dataset.lmSuppressShortcuts = 'true'
  const shadow = host.attachShadow({ mode: 'open' })
  const style = document.createElement('style')
  style.textContent = STYLES
  const root = document.createElement('div')
  root.className = 'tb-root'
  shadow.append(style, root)
  container.append(host)

  const applyTheme = (): void => {
    root.classList.toggle('dark', isDark())
  }
  applyTheme()
  const themes = new MutationObserver(applyTheme)
  themes.observe(document.documentElement, { attributes: true, attributeFilter: ['class', 'data-theme', 'theme'] })
  if (document.body)
    themes.observe(document.body, { attributes: true, attributeFilter: ['class', 'data-jp-theme-light', 'data-vscode-theme-kind'] })
  const system = matchMedia('(prefers-color-scheme: dark)')
  system.addEventListener('change', applyTheme)

  const app = createApp({
    render: () => h(ChartView, { chart: store.chart.value, version: store.version.value, saved: store.saved.value }),
  })
  app.mount(root)
  return () => {
    app.unmount()
    themes.disconnect()
    system.removeEventListener('change', applyTheme)
    host.remove()
  }
}

/** Draws a saved chart; its spec carries every point. */
export function mount(container: HTMLElement, spec: ChartSpec): () => void {
  return draw(container, createStore(spec))
}

// --------------------------------------------------------------------------- the widget

interface Model {
  get: <Name extends keyof Traits>(name: Name) => Traits[Name]
  on: (name: string, callback: (...args: any[]) => void) => void
  off: (name: string, callback: (...args: any[]) => void) => void
  send: (content: unknown) => void
}

interface Traits {
  spec: ChartSpec
  /** Missing from a widget an older tuff-bird showed. */
  saved: boolean | undefined
}

// The model's chart, which every view of it draws, by the spec it was read from. A view drawn late
// (a cell scrolled into view, a second view of the output) so starts with every point appended so far.
const stores = new WeakMap<ChartSpec, Store>()

/** Keeps `store` current with the model; returns what stops it. */
function follow(model: Model, store: Store): () => void {
  stores.set(model.get('spec'), store)
  let syncing = false
  const onSpec = (): void => {
    const spec = model.get('spec')
    store.chart.value = readSpec(spec)
    stores.set(spec, store)
    syncing = false
  }
  const onSaved = (): void => {
    store.saved.value = model.get('saved') === true
  }
  const onMessage = (message: unknown): void => {
    if (!isAppend(message))
      return
    const { landed, gap } = appendPoints(store.chart.value, message)
    if (landed)
      store.version.value += 1
    // The kernel answers with a whole new spec once it is idle.
    if (gap && !syncing) {
      syncing = true
      model.send({ type: 'sync' })
    }
  }
  model.on('change:spec', onSpec)
  model.on('change:saved', onSaved)
  model.on('msg:custom', onMessage)
  return () => {
    model.off('change:spec', onSpec)
    model.off('change:saved', onSaved)
    model.off('msg:custom', onMessage)
  }
}

export default {
  initialize({ model }: { model: Model }): () => void {
    return follow(model, createStore(model.get('spec'), model.get('saved') === true))
  },
  render({ model, el }: { model: Model, el: HTMLElement }): () => void {
    const store = stores.get(model.get('spec'))
    if (store)
      return draw(el, store)
    const own = createStore(model.get('spec'), model.get('saved') === true)
    const stop = follow(model, own)
    const erase = draw(el, own)
    return () => {
      stop()
      erase()
    }
  },
}
