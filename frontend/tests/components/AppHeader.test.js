/**
 * AppHeader 组件测试（示例）
 *
 * 注意：组件测试需要完整模拟 Element Plus 和 Router，
 * Day 4 只展示基础写法，验证组件文件存在。
 * 后续 Days 会引入 vue-test-utils 完善组件渲染测试。
 */
import { describe, it, expect } from 'vitest'
import { existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

describe('AppHeader 组件', () => {
  it('组件文件应该存在', () => {
    const filePath = resolve(__dirname, '../../src/components/layout/AppHeader.vue')
    expect(existsSync(filePath)).toBe(true)
  })
})
