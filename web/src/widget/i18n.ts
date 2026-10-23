// The chart's words, in the browser's language as on the board. The board's own messages stay out:
// every saved chart carries this module.
const zh = {
  smoothing: '平滑',
  show: '显示',
  hide: '隐藏',
  notSaved: '运行已全部停止。这里仍是依赖内核的实时图：再调用一次 show()，图表才会存进笔记本。',
}

type Messages = typeof zh

const en: Messages = {
  smoothing: 'Smoothing',
  show: 'Show',
  hide: 'Hide',
  notSaved: 'The runs have stopped. This output is still the live chart, which needs the kernel: call show() again to save the chart in the notebook.',
}

export const t: Messages = navigator.language.toLowerCase().startsWith('zh') ? zh : en
