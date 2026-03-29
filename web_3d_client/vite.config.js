import { defineConfig } from 'vite'
import { resolve } from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  // 构建配置
  build: {
    // 输出目录 - 指向主项目的 src/web_3d/static/
    outDir: resolve(__dirname, '../src/web_3d/static'),
    // 清空输出目录
    emptyOutDir: true,
    // 资源内联限制 (10KB)
    assetsInlineLimit: 10240,
    // 代码分割配置
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'index.html'),
      },
      output: {
        // 静态资源目录
        assetFileNames: (assetInfo) => {
          const name = assetInfo.name || 'asset'
          if (/\.(png|jpe?g|gif|svg|webp|ico)$/i.test(name)) {
            return `assets/images/[name]-[hash][extname]`
          }
          if (/\.css$/i.test(name)) {
            return `assets/css/[name]-[hash][extname]`
          }
          return `assets/[name]-[hash][extname]`
        },
        // JS 文件
        entryFileNames: 'assets/js/[name]-[hash].js',
        // 代码分割块
        chunkFileNames: 'assets/js/[name]-[hash].js',
      },
    },
    // 压缩配置 (使用默认 esbuild)
    minify: true,
    // 源映射 (生产环境关闭)
    sourcemap: false,
  },
  // 开发服务器配置
  server: {
    port: 5173,
    strictPort: false,
    open: false,
  },
  // 路径别名
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
})
