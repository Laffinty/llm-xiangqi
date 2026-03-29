/**
 * 浏览器兼容性检查器
 * 
 * 检查浏览器是否支持必要的 Web 技术
 */

export class CompatibilityChecker {
  constructor() {
    this.results = {
      webgl2: false,
      websocket: false,
      webaudio: false,
      promises: false,
      fetch: false,
    }
    this.errors = []
  }

  /**
   * 运行所有检查
   * @returns {Object} 检查结果 { supported: boolean, errors: string[] }
   */
  check() {
    this.errors = []

    // 检查 WebGL 2.0
    this.results.webgl2 = this._checkWebGL2()
    if (!this.results.webgl2) {
      this.errors.push('您的浏览器不支持 WebGL 2.0，无法渲染 3D 场景。请使用 Chrome 113+、Edge 113+ 或 Safari 26+。')
    }

    // 检查 WebSocket
    this.results.websocket = this._checkWebSocket()
    if (!this.results.websocket) {
      this.errors.push('您的浏览器不支持 WebSocket，无法实时同步游戏状态。')
    }

    // 检查 Web Audio API
    this.results.webaudio = this._checkWebAudio()
    if (!this.results.webaudio) {
      console.warn('[Compatibility] Web Audio API not supported, sound will be disabled')
    }

    // 检查 Promise
    this.results.promises = this._checkPromises()
    if (!this.results.promises) {
      this.errors.push('您的浏览器不支持现代 JavaScript (Promise)，请更新浏览器。')
    }

    // 检查 Fetch API
    this.results.fetch = this._checkFetch()
    if (!this.results.fetch) {
      this.errors.push('您的浏览器不支持 Fetch API，请更新浏览器。')
    }

    const supported = this.errors.length === 0

    if (supported) {
      console.info('[Compatibility] All checks passed:', this.results)
    } else {
      console.error('[Compatibility] Checks failed:', this.errors)
    }

    return {
      supported,
      errors: this.errors,
      results: this.results,
    }
  }

  /**
   * 检查 WebGL 2.0 支持
   */
  _checkWebGL2() {
    try {
      const canvas = document.createElement('canvas')
      const gl = canvas.getContext('webgl2')
      return gl !== null
    } catch (e) {
      return false
    }
  }

  /**
   * 检查 WebSocket 支持
   */
  _checkWebSocket() {
    return typeof WebSocket !== 'undefined'
  }

  /**
   * 检查 Web Audio API 支持
   */
  _checkWebAudio() {
    return typeof AudioContext !== 'undefined' || typeof webkitAudioContext !== 'undefined'
  }

  /**
   * 检查 Promise 支持
   */
  _checkPromises() {
    return typeof Promise !== 'undefined'
  }

  /**
   * 检查 Fetch API 支持
   */
  _checkFetch() {
    return typeof fetch !== 'undefined'
  }

  /**
   * 获取浏览器信息
   */
  static getBrowserInfo() {
    const ua = navigator.userAgent
    const info = {
      userAgent: ua,
      language: navigator.language,
      platform: navigator.platform,
      vendor: navigator.vendor,
    }

    // 尝试识别浏览器
    if (ua.includes('Chrome') && !ua.includes('Edg')) {
      info.name = 'Chrome'
      const match = ua.match(/Chrome\/(\d+)/)
      info.version = match ? parseInt(match[1]) : null
    } else if (ua.includes('Edg')) {
      info.name = 'Edge'
      const match = ua.match(/Edg\/(\d+)/)
      info.version = match ? parseInt(match[1]) : null
    } else if (ua.includes('Safari') && !ua.includes('Chrome')) {
      info.name = 'Safari'
      const match = ua.match(/Version\/(\d+)/)
      info.version = match ? parseInt(match[1]) : null
    } else if (ua.includes('Firefox')) {
      info.name = 'Firefox'
      const match = ua.match(/Firefox\/(\d+)/)
      info.version = match ? parseInt(match[1]) : null
    } else {
      info.name = 'Unknown'
      info.version = null
    }

    return info
  }

  /**
   * 检查是否为支持的浏览器版本
   */
  static isSupportedBrowser() {
    const info = this.getBrowserInfo()
    const minVersions = {
      'Chrome': 113,
      'Edge': 113,
      'Safari': 26,
      'Firefox': 141,
    }

    const minVersion = minVersions[info.name]
    if (!minVersion) return false
    if (!info.version) return false

    return info.version >= minVersion
  }

  /**
   * 显示兼容性错误页面
   */
  static showErrorPage(errors) {
    const container = document.getElementById('game-container') || document.body
    
    const errorHtml = `
      <div style="
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: #0f0f1a;
        color: #fff;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 40px;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        z-index: 10000;
      ">
        <h1 style="color: #f44336; margin-bottom: 20px;">⚠️ 浏览器不兼容</h1>
        <div style="max-width: 600px; text-align: left;">
          ${errors.map(e => `<p style="margin: 10px 0; color: #ccc;">• ${e}</p>`).join('')}
        </div>
        <div style="margin-top: 30px; color: #888; font-size: 0.9rem;">
          <p>推荐浏览器：</p>
          <ul style="text-align: left; line-height: 1.8;">
            <li>Google Chrome 113 或更高版本</li>
            <li>Microsoft Edge 113 或更高版本</li>
            <li>Safari 26 或更高版本</li>
          </ul>
        </div>
      </div>
    `

    container.innerHTML = errorHtml
  }
}
