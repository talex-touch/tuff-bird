import '@talex-touch/tuffex/base.css'
// TxLearningCurve is imported from its own module (see ChartCard.vue), so its styles come by hand.
import '@talex-touch/tuffex/charts/style.css'
import './app.css'
import { createApp } from 'vue'
import App from './App.vue'

const darkQuery = matchMedia('(prefers-color-scheme: dark)')
const applyTheme = (): void => {
  document.documentElement.classList.toggle('dark', darkQuery.matches)
}
applyTheme()
darkQuery.addEventListener('change', applyTheme)
document.documentElement.lang = navigator.language.toLowerCase().startsWith('zh') ? 'zh' : 'en'

createApp(App).mount('#app')
