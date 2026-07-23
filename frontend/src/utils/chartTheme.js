/**
 * ECharts 主题助手：从 --vp-* 设计 token 取色，提供玻璃 tooltip、
 * 渐变面积填充、环形中心文案等统一配置。主题切换后需重渲染图表。
 */
import { LinearGradient } from 'echarts/lib/util/graphic'

export function chartPalette() {
  const style = getComputedStyle(document.documentElement)
  const read = (name, fallback) => style.getPropertyValue(name).trim() || fallback
  return {
    text: read('--vp-text', '#1d1d1f'),
    muted: read('--vp-muted', '#6e6e73'),
    border: read('--vp-border', '#e5e5e7'),
    surface: read('--vp-surface', '#fff'),
    primary: read('--vp-primary', '#2b7fff'),
    cyan: read('--vp-accent-cyan', '#06b6d4'),
    success: read('--vp-success', '#12b76a'),
    warning: read('--vp-warning', '#d97706'),
    danger: read('--vp-danger', '#d92d20'),
    isDark: document.documentElement.classList.contains('dark'),
  }
}

export const SERIES_COLORS = [
  '#0071e3',
  '#34c759',
  '#ff9f0a',
  '#af52de',
  '#5ac8fa',
  '#ff375f',
  '#64d2ff',
  '#bf5af2',
  '#8e8e93',
]

/** 玻璃拟态 tooltip：半透明底 + 模糊 + 细亮边。 */
export function glassTooltip(colors, extra = {}) {
  return {
    backgroundColor: colors.isDark ? 'rgba(13, 20, 36, 0.86)' : 'rgba(255, 255, 255, 0.92)',
    borderColor: colors.isDark ? 'rgba(255, 255, 255, 0.12)' : colors.border,
    borderWidth: 1,
    padding: [10, 14],
    textStyle: { color: colors.text, fontSize: 12 },
    extraCssText:
      'backdrop-filter: blur(12px) saturate(150%);-webkit-backdrop-filter: blur(12px) saturate(150%);' +
      'border-radius: 10px;box-shadow: 0 8px 28px rgba(0, 0, 0, 0.24);',
    ...extra,
  }
}

/** 折线面积渐变填充：主色自上而下淡出为透明。 */
export function areaGradient(color, topOpacity = 0.32) {
  return new LinearGradient(0, 0, 0, 1, [
    { offset: 0, color: withOpacity(color, topOpacity) },
    { offset: 1, color: withOpacity(color, 0) },
  ])
}

/** 柱状图纵向渐变。 */
export function barGradient(color, bottomOpacity = 0.55) {
  return new LinearGradient(0, 0, 0, 1, [
    { offset: 0, color },
    { offset: 1, color: withOpacity(color, bottomOpacity) },
  ])
}

function withOpacity(color, opacity) {
  if (color.startsWith('#')) {
    const hex = color.slice(1)
    const full = hex.length === 3 ? hex.replace(/(.)/g, '$1$1') : hex
    const num = parseInt(full, 16)
    const r = (num >> 16) & 255
    const g = (num >> 8) & 255
    const b = num & 255
    return `rgba(${r}, ${g}, ${b}, ${opacity})`
  }
  if (color.startsWith('rgba')) return color.replace(/[\d.]+\)$/, `${opacity})`)
  return color
}

/** 无数据占位文案。 */
export function emptyChartGraphic(message, colors = chartPalette()) {
  return [
    {
      type: 'text',
      left: 'center',
      top: 'middle',
      style: { text: message, fill: colors.muted, fontSize: 13 },
    },
  ]
}

/** 环形图中心大数字 + 说明文案。center 与饼图 series.center 保持一致。 */
export function donutCenterGraphic(value, label, colors = chartPalette(), center = ['30%', '50%']) {
  return [
    {
      type: 'text',
      silent: true,
      left: center[0],
      top: '42%',
      style: {
        text: String(value),
        fill: colors.text,
        fontSize: 26,
        fontWeight: 700,
        align: 'center',
        verticalAlign: 'middle',
      },
    },
    {
      type: 'text',
      silent: true,
      left: center[0],
      top: '56%',
      style: {
        text: label,
        fill: colors.muted,
        fontSize: 12,
        align: 'center',
        verticalAlign: 'middle',
      },
    },
  ]
}
