/**
 * Markdown 渲染工具
 * 用于 Day 11 智能体对话中 AI 回复的 Markdown 渲染
 */
import MarkdownIt from 'markdown-it'

// 创建 markdown-it 实例，启用 HTML 支持
const md = new MarkdownIt({
  html: false,        // 禁用 HTML 标签（安全考虑）
  linkify: true,      // 自动将 URL 转为链接
  typographer: true,  // 启用排版优化（如引号替换）
  breaks: true,       // 将 \n 转为 <br>
})

/**
 * 将 Markdown 文本渲染为 HTML
 * @param {string} text - Markdown 文本
 * @returns {string} 渲染后的 HTML 字符串
 */
export function renderMarkdown(text) {
  if (!text) return ''
  // Agent 的结构化结果以文字和数据为主。清除装饰性 emoji，避免历史消息或模型偶发
  // 输出破坏后台工作台的专业视觉风格；业务文字、数字与中文均会原样保留。
  const cleanText = String(text)
    .replace(/[\p{Extended_Pictographic}\p{Regional_Indicator}]/gu, '')
    .replace(/[\u200D\uFE0E\uFE0F]/g, '')

  // markdown-it 默认没有表格容器。为横向空间不足的会话内容增加滚动容器，
  // 使较宽的结果表不会挤压聊天列或把单元格拆得难以阅读。
  return md.render(cleanText)
    .replace(/<table>/g, '<div class="markdown-table-wrap"><table>')
    .replace(/<\/table>/g, '</table></div>')
}

export default md
