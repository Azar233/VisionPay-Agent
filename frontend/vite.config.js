import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'
import os from 'node:os'

function findLanAddress() {
  const candidates = []
  const blockedNames = /virtual|vmware|vbox|docker|wsl|loopback|bluetooth|tailscale/i
  const wirelessNames = /wi-?fi|wlan|wireless|无线/i
  const wiredNames = /ethernet|以太网/i

  for (const [name, addresses] of Object.entries(os.networkInterfaces())) {
    for (const address of addresses || []) {
      if (address.family !== 'IPv4' || address.internal || blockedNames.test(name)) continue
      if (!/^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/.test(address.address)) continue
      const score = wirelessNames.test(name) ? 20 : wiredNames.test(name) ? 10 : 0
      candidates.push({ address: address.address, score })
    }
  }

  return candidates.sort((left, right) => right.score - left.score)[0]?.address || ''
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const lanAddress = findLanAddress()
  const checkoutPublicOrigin =
    env.VITE_CHECKOUT_PUBLIC_ORIGIN || (lanAddress ? `http://${lanAddress}:5173` : '')

  return {
    plugins: [vue()],
    define: {
      'import.meta.env.VITE_CHECKOUT_PUBLIC_ORIGIN': JSON.stringify(checkoutPublicOrigin),
    },
    //路径别名
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    //css预处理器配置
    css: {
      preprocessorOptions: {
        scss: {
          additionalData: `@use "@/assets/styles/variables.scss" as *;`,
        },
      },
    },
    //开发服务器配置
    server: {
      port: 5173,
      open: true, // 启动时⾃动打开浏览器
      // API 代理：将 /api 开头的请求转发到后端
      proxy: {
        '/api': {
          target: 'http://localhost:8000',
          changeOrigin: true,
          ws: true,
        },
        '/media': {
          target: 'http://localhost:8000',
          changeOrigin: true,
        },
      },
    },
    test: {
      // 使用 happy-dom 模拟浏览器环境
      environment: 'happy-dom',
      // 全局 setup 文件
      setupFiles: ['./tests/setup.js'],
      // 测试文件匹配模式
      include: ['tests/**/*.{test,spec}.{js,ts}'],
      // 覆盖率(可选)
      coverage: {
        provider: 'v8',
        reporter: ['text', 'html'],
      },
    },
  }
})
