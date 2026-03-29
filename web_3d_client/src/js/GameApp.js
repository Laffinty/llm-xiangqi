/**
 * 游戏应用主类
 * 
 * 功能:
 * - 整合 WebSocket、状态管理、3D 渲染
 * - 处理游戏消息流程
 * - UI 状态更新
 */

import { WebSocketClient, PROTOCOL_VERSION } from './WebSocketClient.js'
import { GameStateManager, GAME_STATUS } from './GameStateManager.js'
import { SceneManager } from './SceneManager.js'

export class GameApp {
  constructor(containerId, options = {}) {
    this.container = document.getElementById(containerId)
    if (!this.container) {
      throw new Error(`Container #${containerId} not found`)
    }

    this.options = {
      wsUrl: options.wsUrl || `ws://${window.location.host}/ws`,
      autoConnect: options.autoConnect !== false,
      ...options,
    }

    // 组件
    this.wsClient = null
    this.stateManager = null
    this.sceneManager = null

    // UI 元素
    this.ui = {}

    // 动画持续时间
    this.animationDuration = 0.5

    // 音效开关状态
    this._soundEnabled = true

    // 初始化
    this._initUI()
    this._initComponents()
  }

  /**
   * 初始化 UI
   */
  _initUI() {
    // 状态面板
    this.ui.statusPanel = document.getElementById('status-panel')
    this.ui.connectionStatus = document.getElementById('connection-status')
    this.ui.turnInfo = document.getElementById('turn-info')
    this.ui.redPlayer = document.getElementById('red-player')
    this.ui.blackPlayer = document.getElementById('black-player')
    this.ui.moveHistory = document.getElementById('move-history')
    this.ui.gameResult = document.getElementById('game-result')

    // 3D 画布
    this.canvas = document.getElementById('game-canvas')
    if (!this.canvas) {
      throw new Error('Canvas #game-canvas not found')
    }

    // 设置画布尺寸
    this._resizeCanvas()
    window.addEventListener('resize', () => this._resizeCanvas())

    // 初始化控制按钮
    this._initControls()
  }

  /**
   * 初始化控制按钮
   */
  _initControls() {
    // 重置相机按钮
    const btnResetCamera = document.getElementById('btn-reset-camera')
    if (btnResetCamera) {
      btnResetCamera.addEventListener('click', () => {
        if (this.sceneManager) {
          this.sceneManager.resetCamera()
        }
      })
    }

    // 音效开关按钮
    const btnToggleSound = document.getElementById('btn-toggle-sound')
    if (btnToggleSound) {
      btnToggleSound.addEventListener('click', () => {
        this._soundEnabled = !this._soundEnabled
        if (this.sceneManager && this.sceneManager.sounds) {
          this.sceneManager.sounds.setEnabled(this._soundEnabled)
        }
        // 更新按钮状态
        btnToggleSound.classList.toggle('muted', !this._soundEnabled)
        const icon = btnToggleSound.querySelector('span')
        if (icon) {
          icon.textContent = this._soundEnabled ? '🔊' : '🔇'
        }
      })
    }

    // 音量滑块
    const volumeSlider = document.getElementById('volume-slider')
    if (volumeSlider) {
      volumeSlider.addEventListener('input', (e) => {
        const volume = parseInt(e.target.value) / 100
        if (this.sceneManager && this.sceneManager.sounds) {
          this.sceneManager.sounds.setVolume(volume)
        }
      })
    }

    // 帮助按钮
    const btnHelp = document.getElementById('btn-help')
    if (btnHelp) {
      btnHelp.addEventListener('click', () => {
        alert(`操作说明:
- 鼠标左键拖拽: 旋转视角
- 鼠标右键拖拽: 平移视角
- 滚轮: 缩放
- 点击棋子: 选中
- 点击按钮: 重置相机/开关音效

快捷键:
- R: 重置相机
- M: 静音/取消静音`)
      })
    }

    // 键盘快捷键
    window.addEventListener('keydown', (e) => {
      switch (e.key.toLowerCase()) {
        case 'r':
          if (this.sceneManager) {
            this.sceneManager.resetCamera()
          }
          break
        case 'm':
          this._soundEnabled = !this._soundEnabled
          if (this.sceneManager && this.sceneManager.sounds) {
            this.sceneManager.sounds.setEnabled(this._soundEnabled)
          }
          // 更新按钮状态
          if (btnToggleSound) {
            btnToggleSound.classList.toggle('muted', !this._soundEnabled)
            const icon = btnToggleSound.querySelector('span')
            if (icon) {
              icon.textContent = this._soundEnabled ? '🔊' : '🔇'
            }
          }
          break
      }
    })
  }

  /**
   * 调整画布尺寸
   */
  _resizeCanvas() {
    const rect = this.container.getBoundingClientRect()
    this.canvas.width = rect.width
    this.canvas.height = rect.height
  }

  /**
   * 初始化组件
   */
  _initComponents() {
    // 状态管理
    this.stateManager = new GameStateManager()
    this.stateManager.addListener((type, data) => {
      this._onStateChange(type, data)
    })

    // WebSocket 客户端
    this.wsClient = new WebSocketClient(this.options.wsUrl, {
      onOpen: () => this._onWsOpen(),
      onClose: () => this._onWsClose(),
      onMessage: (msg) => this._onWsMessage(msg),
      onError: (err) => this._onWsError(err),
      onStateChange: (state) => this._onConnectionStateChange(state),
    })

    // 3D 场景 (延迟初始化，等待 WebGPU 检测)
    this._initScene()
  }

  /**
   * 初始化 3D 场景
   */
  async _initScene() {
    try {
      this.sceneManager = new SceneManager(this.canvas, {
        shadowMapSize: 2048,
        cameraPosition: [8, 12, 12],
        lightFollowsCamera: true,
      })

      await this.sceneManager.init()

      // 显示渲染器信息
      this._showRendererInfo()

    } catch (error) {
      console.error('[GameApp] Failed to init scene:', error)
      this._showError('3D 渲染器初始化失败: ' + error.message)
    }
  }

  /**
   * 显示渲染器信息
   */
  _showRendererInfo() {
    const info = document.getElementById('renderer-info')
    if (info) {
      const type = this.sceneManager.rendererType.toUpperCase()
      info.textContent = `渲染器: ${type}`
      info.className = `renderer-badge ${this.sceneManager.rendererType}`
    }
  }

  /**
   * 启动应用
   */
  async start() {
    console.info('[GameApp] Starting...')

    // 等待场景初始化
    if (!this.sceneManager) {
      let attempts = 0
      while (!this.sceneManager && attempts < 50) {
        await new Promise(r => setTimeout(r, 100))
        attempts++
      }
    }

    // 连接 WebSocket
    if (this.options.autoConnect) {
      this.wsClient.connect()
    }

    console.info('[GameApp] Started')
  }

  /**
   * 停止应用
   */
  stop() {
    console.info('[GameApp] Stopping...')

    if (this.wsClient) {
      this.wsClient.close()
    }

    if (this.sceneManager) {
      this.sceneManager.dispose()
    }

    console.info('[GameApp] Stopped')
  }

  /**
   * WebSocket 连接成功
   */
  _onWsOpen() {
    console.info('[GameApp] WebSocket connected')
  }

  /**
   * WebSocket 断开
   */
  _onWsClose() {
    console.info('[GameApp] WebSocket disconnected')
  }

  /**
   * WebSocket 错误
   */
  _onWsError(error) {
    console.error('[GameApp] WebSocket error:', error)
  }

  /**
   * 连接状态变化
   */
  _onConnectionStateChange(state) {
    if (!this.ui.connectionStatus) return

    const statusMap = {
      'connected': { text: '已连接', class: 'connected' },
      'disconnected': { text: '已断开', class: 'disconnected' },
      'reconnecting': { text: '重连中...', class: 'reconnecting' },
      'failed': { text: '连接失败', class: 'failed' },
    }

    const info = statusMap[state] || { text: state, class: '' }
    this.ui.connectionStatus.textContent = info.text
    this.ui.connectionStatus.className = `status-badge ${info.class}`
  }

  /**
   * 处理 WebSocket 消息
   */
  _onWsMessage(message) {
    console.debug('[GameApp] Received:', message.type)

    switch (message.type) {
      case 'game.init':
        this._handleGameInit(message.payload)
        break

      case 'game.move':
        this._handleGameMove(message.payload)
        break

      case 'game.game_over':
        this._handleGameOver(message.payload)
        break

      case 'server.error':
        this._handleServerError(message.payload)
        break

      default:
        console.warn('[GameApp] Unknown message type:', message.type)
    }
  }

  /**
   * 处理游戏初始化
   */
  _handleGameInit(state) {
    console.info('[GameApp] Game init:', state)

    // 更新状态
    this.stateManager.initFromServer(state)

    // 更新 UI
    this._updateUI()

    // 更新 3D 场景
    if (this.sceneManager) {
      const layout = this.stateManager.getBoardLayout()
      this.sceneManager.updateBoard(layout)
    }

    // 显示游戏结果 (如果游戏已结束)
    if (state.status === GAME_STATUS.FINISHED) {
      this._showGameResult(state.result, state.result_reason)
    }
  }

  /**
   * 处理走步
   */
  async _handleGameMove(moveData) {
    console.info('[GameApp] Move:', moveData)

    // 更新状态
    this.stateManager.handleMove(moveData)

    // 更新 UI
    this._updateUI()

    // 更新 3D 场景
    if (this.sceneManager) {
      const { from_pos, to_pos } = moveData

      // 高亮最后走法
      this.sceneManager.highlightLastMove(from_pos, to_pos)

      // 移动棋子动画 (异步等待完成)
      try {
        await this.sceneManager.movePiece(from_pos, to_pos, this.animationDuration)
      } catch (error) {
        console.error('[GameApp] Move animation failed:', error)
      }
    }
  }

  /**
   * 处理游戏结束
   */
  _handleGameOver(gameOverData) {
    console.info('[GameApp] Game over:', gameOverData)

    // 更新状态
    this.stateManager.handleGameOver(gameOverData)

    // 显示结果
    this._showGameResult(gameOverData.result, gameOverData.result_reason)
  }

  /**
   * 处理服务器错误
   */
  _handleServerError(error) {
    console.error('[GameApp] Server error:', error)
    this._showError(`服务器错误: ${error.message} (${error.code})`)
  }

  /**
   * 状态变化回调
   */
  _onStateChange(type, data) {
    // 状态变化时的额外处理
    console.debug('[GameApp] State change:', type, data)
  }

  /**
   * 更新 UI
   */
  _updateUI() {
    if (!this.stateManager) return

    const sm = this.stateManager

    // 回合信息
    if (this.ui.turnInfo) {
      this.ui.turnInfo.textContent = sm.getTurnDisplay()
    }

    // 玩家信息
    if (this.ui.redPlayer) {
      const red = sm.players.Red
      this.ui.redPlayer.innerHTML = `
        <div class="player-name">${red.name}</div>
        <div class="player-model">${red.model}</div>
      `
      this.ui.redPlayer.className = `player-card red ${sm.turn === 'Red' && sm.status === GAME_STATUS.PLAYING ? 'active' : ''}`
    }

    if (this.ui.blackPlayer) {
      const black = sm.players.Black
      this.ui.blackPlayer.innerHTML = `
        <div class="player-name">${black.name}</div>
        <div class="player-model">${black.model}</div>
      `
      this.ui.blackPlayer.className = `player-card black ${sm.turn === 'Black' && sm.status === GAME_STATUS.PLAYING ? 'active' : ''}`
    }

    // 走步历史
    if (this.ui.moveHistory) {
      this.ui.moveHistory.textContent = sm.formatMoveHistory()
    }
  }

  /**
   * 显示游戏结果
   */
  _showGameResult(result, reason) {
    if (!this.ui.gameResult) return

    const resultText = {
      'red_win': '红方胜利',
      'black_win': '黑方胜利',
      'draw': '平局',
    }[result] || result

    this.ui.gameResult.innerHTML = `
      <div class="result-title">游戏结束</div>
      <div class="result-text">${resultText}</div>
      <div class="result-reason">${reason || ''}</div>
    `
    this.ui.gameResult.className = 'game-result show'
  }

  /**
   * 显示错误
   */
  _showError(message) {
    console.error('[GameApp]', message)

    const errorDiv = document.getElementById('error-message')
    if (errorDiv) {
      errorDiv.textContent = message
      errorDiv.style.display = 'block'
      setTimeout(() => {
        errorDiv.style.display = 'none'
      }, 5000)
    }
  }
}
