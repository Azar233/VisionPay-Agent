import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
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
      },
    },
  },
  test: {
    // 使用 happy-dom 模拟浏览器环境
    environment: "happy-dom",
    // 全局 setup 文件
    setupFiles: ["./tests/setup.js"],
    // 测试文件匹配模式
    include: ["tests/**/*.{test,spec}.{js,ts}"],
    // 覆盖率(可选)
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
    },
  },
})
