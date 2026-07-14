import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const viteCli = fileURLToPath(new URL('../node_modules/vite/bin/vite.js', import.meta.url))

function optionValue(name, fallback) {
  const exactIndex = process.argv.indexOf(name)
  if (exactIndex >= 0 && process.argv[exactIndex + 1]) return process.argv[exactIndex + 1]
  const inline = process.argv.find((item) => item.startsWith(`${name}=`))
  return inline ? inline.slice(name.length + 1) : fallback
}

const host = optionValue('--host', '127.0.0.1')
const services = [
  {
    name: 'developer',
    args: [viteCli, '--host', host, '--port', '5173'],
  },
  {
    name: 'checkout',
    args: [viteCli, '--mode', 'checkout', '--host', host, '--port', '5174', '--open', '/checkout'],
  },
]

const children = services.map(({ name, args }) => {
  const child = spawn(process.execPath, args, {
    cwd: fileURLToPath(new URL('..', import.meta.url)),
    stdio: 'inherit',
    env: process.env,
  })
  child.serviceName = name
  return child
})

let stopping = false

function stopAll(exitCode = 0) {
  if (stopping) return
  stopping = true
  for (const child of children) {
    if (!child.killed) child.kill()
  }
  process.exitCode = exitCode
}

for (const child of children) {
  child.on('error', (error) => {
    console.error(`[dev:${child.serviceName}] 启动失败:`, error.message)
    stopAll(1)
  })
  child.on('exit', (code, signal) => {
    if (stopping) return
    if (signal) console.error(`[dev:${child.serviceName}] 被信号 ${signal} 终止`)
    else if (code !== 0) console.error(`[dev:${child.serviceName}] 退出，代码 ${code}`)
    stopAll(code || 0)
  })
}

process.on('SIGINT', () => stopAll(0))
process.on('SIGTERM', () => stopAll(0))
