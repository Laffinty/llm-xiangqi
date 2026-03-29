/**
 * Web 3D 中国象棋 - 入口文件
 * 
 * 启动 3D 象棋可视化应用
 */

import { GameApp } from './js/GameApp.js'
import { CompatibilityChecker } from './js/CompatibilityChecker.js'
import './style.css'

// 等待 DOM 加载
document.addEventListener('DOMContentLoaded', async () => {
  console.info('[Main] Web 3D Xiangqi starting...')

  // 首先检查浏览器兼容性
  const checker = new CompatibilityChecker()
  const checkResult = checker.check()

  if (!checkResult.supported) {
    CompatibilityChecker.showErrorPage(checkResult.errors)
    return
  }

  // 警告不支持的浏览器版本
  if (!CompatibilityChecker.isSupportedBrowser()) {
    const info = CompatibilityChecker.getBrowserInfo()
    console.warn(`[Main] Browser ${info.name} ${info.version} may not be fully supported`)
  }

  // 隐藏加载动画
  const hideLoading = () => {
    const loading = document.getElementById('loading')
    if (loading) {
      loading.style.opacity = '0'
      setTimeout(() => loading.style.display = 'none', 300)
    }
  }

  try {
    // 创建应用
    const app = new GameApp('game-container', {
      wsUrl: `ws://${window.location.host}/ws`,
      autoConnect: true,
    })

    // 启动
    await app.start()
    
    // 隐藏加载指示器
    hideLoading()

    // 全局引用 (调试使用)
    window.gameApp = app

    // 页面卸载时清理
    window.addEventListener('beforeunload', () => {
      app.stop()
    })
    
    console.info('[Main] Web 3D Xiangqi started successfully')
    
  } catch (error) {
    console.error('[Main] Failed to start app:', error)
    hideLoading()
    showFatalError('应用启动失败: ' + error.message)
  }
})

/**
 * 显示致命错误
 */
function showFatalError(message) {
  const container = document.getElementById('game-container')
  if (container) {
    container.innerHTML = `
      <div class="fatal-error">
        <h2>⚠️ 应用错误</h2>
        <p>${message}</p>
        <button onclick="location.reload()">刷新页面</button>
      </div>
    `
  }
}
