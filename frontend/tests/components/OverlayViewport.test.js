import { readdirSync, readFileSync } from 'node:fs'
import { extname, join } from 'node:path'
import { describe, expect, it } from 'vitest'

const sourceRoot = join(process.cwd(), 'src')
const globalStyles = readFileSync(join(sourceRoot, 'assets/styles/global.scss'), 'utf8')

function vueFiles(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name)
    if (entry.isDirectory()) return vueFiles(path)
    return extname(entry.name) === '.vue' ? [path] : []
  })
}

describe('Element Plus modal surfaces', () => {
  it('teleports every dialog and drawer out of page scroll containers', () => {
    const missing = []
    const tagPattern = /<el-(?:dialog|drawer)\b[\s\S]*?>/g

    for (const path of vueFiles(sourceRoot)) {
      const tags = readFileSync(path, 'utf8').match(tagPattern) || []
      for (const tag of tags) {
        if (!/\bappend-to-body\b/.test(tag)) missing.push(path)
      }
    }

    expect(missing).toEqual([])
  })

  it('applies a glass backdrop to dialogs, drawers, and message boxes', () => {
    expect(globalStyles).toContain('body > .el-overlay.el-modal-dialog')
    expect(globalStyles).toContain('body > .el-overlay.el-modal-drawer')
    expect(globalStyles).toContain('body > .el-overlay.is-message-box')
    expect(globalStyles).toContain('backdrop-filter: blur(var(--vp-modal-backdrop-blur))')
  })
})
