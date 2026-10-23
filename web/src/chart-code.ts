import { board, prefs, runs, seriesOf, ui } from './store'

// The defaults of tuffbird's plot() and chart(), left out of the code.
const DEFAULT_SMOOTHING = 0.6

/** Python that draws `tag` with the board's settings: as a figure for a paper, and as this chart in one file. */
export function chartCode(tag: string): string {
  // Named as `tuff-bird plot` names its output.
  const name = tag.replace(/[^\p{L}\p{N}\p{M}_.-]+/gu, '-').replace(/^-+|-+$/g, '') || 'chart'
  const shared: string[] = []
  // tuffbird merges each directory's runs unless told not to; with no directories, there is nothing to merge.
  if (!prefs.mergeGroups && runs.value.some(run => run.parent))
    shared.push('group_by=None')
  const smoothing = Number(prefs.smoothing.toFixed(2))
  if (smoothing !== DEFAULT_SMOOTHING)
    shared.push(`smoothing=${smoothing}`)
  const chart = [...shared]
  if (!prefs.showRaw)
    chart.push('show_raw=False')
  if (prefs.logX)
    chart.push('log_x=True')

  // A JSON string is a Python string literal with the same value.
  const call = (options: string[]): string => [JSON.stringify(tag), ...options].join(', ')
  const lines = ['import tuffbird', '', `exp = tuffbird.load(${JSON.stringify(board.logdir)})`]
  const hidden = runs.value.filter(run => ui.hidden.has(run.id) && seriesOf(tag, run.id)?.points.length).length
  if (hidden)
    lines.push(`# The board hides ${hidden === 1 ? '1 run' : `${hidden} runs`} of this chart; this code draws every run.`)
  lines.push(
    '# A figure for a paper (pip install "tuff-bird[plot]")',
    `exp.plot(${call(shared)}).savefig(${JSON.stringify(`${name}.pdf`)})`,
    '# This chart, in one HTML file that opens offline',
    `exp.chart(${call(chart)}).save(${JSON.stringify(`${name}.html`)})`,
  )
  return `${lines.join('\n')}\n`
}

/** Puts `text` on the clipboard; returns whether it got there. */
export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  }
  catch {
    // A board opened over plain HTTP from another machine has no clipboard API.
    const focused = document.activeElement
    const area = document.createElement('textarea')
    area.value = text
    area.setAttribute('readonly', '')
    area.style.cssText = 'position:fixed;top:0;left:0;opacity:0'
    document.body.append(area)
    area.select()
    try {
      return document.execCommand('copy')
    }
    catch {
      return false
    }
    finally {
      area.remove()
      if (focused instanceof HTMLElement)
        focused.focus()
    }
  }
}
