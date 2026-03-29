/**
 * WebSocket 客户端
 * 
 * 功能:
 * - 与服务器建立 WebSocket 连接
 * - 自动断线重连机制 (指数退避)
 * - 心跳检测 (ping/pong)
 * - 消息类型分发
 */

// 协议版本
const PROTOCOL_VERSION = '1.0.0'

// WebSocket 状态
const WS_STATE = {
  CONNECTING: 0,
  OPEN: 1,
  CLOSING: 2,
  CLOSED: 3,
}

export class WebSocketClient {
  /**
   * @param {string} url - WebSocket URL
   * @param {Object} options - 配置选项
   */
  constructor(url, options = {}) {
    this.url = url
    this.ws = null
    
    // 重连配置
    this.reconnectAttempts = 0
    this.maxReconnectAttempts = options.maxReconnectAttempts || 10
    this.reconnectDelay = options.reconnectDelay || 1000 // 初始延迟 1s
    this.maxReconnectDelay = options.maxReconnectDelay || 30000 // 最大延迟 30s
    this.reconnectBackoffMultiplier = options.reconnectBackoffMultiplier || 1.5
    
    // 心跳配置
    this.heartbeatInterval = options.heartbeatInterval || 30000 // 30s
    this.heartbeatTimeout = options.heartbeatTimeout || 10000 // 10s
    this._heartbeatTimer = null
    this._pongTimeout = null
    this._lastPingId = 0
    
    // 状态
    this._isManualClose = false
    this._isConnected = false
    
    // 事件回调
    this.onOpen = options.onOpen || null
    this.onMessage = options.onMessage || null
    this.onClose = options.onClose || null
    this.onError = options.onError || null
    this.onReconnect = options.onReconnect || null
    this.onStateChange = options.onStateChange || null // 连接状态变化
  }

  /**
   * 获取当前连接状态
   */
  get state() {
    return this.ws ? this.ws.readyState : WS_STATE.CLOSED
  }

  get isConnected() {
    return this._isConnected
  }

  /**
   * 建立 WebSocket 连接
   */
  connect() {
    if (this.ws && (this.ws.readyState === WS_STATE.CONNECTING || this.ws.readyState === WS_STATE.OPEN)) {
      console.warn('[WS] Already connecting or connected')
      return
    }

    this._isManualClose = false
    
    try {
      console.info(`[WS] Connecting to ${this.url}`)
      this.ws = new WebSocket(this.url)
      this._bindEvents()
    } catch (error) {
      console.error('[WS] Connection error:', error)
      this._scheduleReconnect()
    }
  }

  /**
   * 绑定 WebSocket 事件
   */
  _bindEvents() {
    this.ws.onopen = (event) => {
      console.info('[WS] Connected')
      this._isConnected = true
      this.reconnectAttempts = 0
      this.reconnectDelay = 1000
      
      // 发送客户端就绪消息
      this.send({
        type: 'client.ready',
        protocol_version: PROTOCOL_VERSION,
        client_id: this._generateClientId(),
      })
      
      // 启动心跳
      this._startHeartbeat()
      
      if (this.onOpen) this.onOpen(event)
      if (this.onStateChange) this.onStateChange('connected')
    }

    this.ws.onmessage = (event) => {
      this._handleMessage(event.data)
    }

    this.ws.onclose = (event) => {
      console.warn(`[WS] Disconnected (code: ${event.code}, reason: ${event.reason})`)
      this._isConnected = false
      this._stopHeartbeat()
      
      if (this.onClose) this.onClose(event)
      if (this.onStateChange) this.onStateChange('disconnected')
      
      if (!this._isManualClose) {
        this._scheduleReconnect()
      }
    }

    this.ws.onerror = (error) => {
      console.error('[WS] Error:', error)
      if (this.onError) this.onError(error)
    }
  }

  /**
   * 处理收到的消息
   */
  _handleMessage(data) {
    try {
      const message = JSON.parse(data)
      
      // 处理 pong 响应
      if (message.type === 'server.pong') {
        this._handlePong(message)
        return
      }
      
      // 处理错误消息
      if (message.type === 'server.error') {
        console.error('[WS] Server error:', message.payload)
      }
      
      // 分发到外部处理器
      if (this.onMessage) {
        this.onMessage(message)
      }
    } catch (error) {
      console.error('[WS] Failed to parse message:', error, data)
    }
  }

  /**
   * 发送消息
   */
  send(data) {
    if (!this.ws || this.ws.readyState !== WS_STATE.OPEN) {
      console.warn('[WS] Cannot send, connection not open')
      return false
    }
    
    try {
      const message = typeof data === 'string' ? data : JSON.stringify(data)
      this.ws.send(message)
      return true
    } catch (error) {
      console.error('[WS] Send error:', error)
      return false
    }
  }

  /**
   * 关闭连接
   */
  close() {
    this._isManualClose = true
    this._stopHeartbeat()
    
    if (this.ws) {
      try {
        this.ws.close(1000, 'Client closing')
      } catch (error) {
        console.error('[WS] Close error:', error)
      }
      this.ws = null
    }
    
    this._isConnected = false
  }

  /**
   * 安排重连
   */
  _scheduleReconnect() {
    if (this._isManualClose) {
      return
    }
    
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('[WS] Max reconnect attempts reached')
      if (this.onStateChange) this.onStateChange('failed')
      return
    }

    const delay = Math.min(
      this.reconnectDelay * Math.pow(this.reconnectBackoffMultiplier, this.reconnectAttempts),
      this.maxReconnectDelay
    )
    this.reconnectAttempts++

    console.info(`[WS] Reconnecting in ${Math.round(delay)}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`)
    
    if (this.onStateChange) this.onStateChange('reconnecting')
    if (this.onReconnect) this.onReconnect(this.reconnectAttempts, delay)

    setTimeout(() => this.connect(), delay)
  }

  /**
   * 启动心跳检测
   */
  _startHeartbeat() {
    this._stopHeartbeat()
    
    this._heartbeatTimer = setInterval(() => {
      this._sendPing()
    }, this.heartbeatInterval)
  }

  /**
   * 停止心跳检测
   */
  _stopHeartbeat() {
    if (this._heartbeatTimer) {
      clearInterval(this._heartbeatTimer)
      this._heartbeatTimer = null
    }
    if (this._pongTimeout) {
      clearTimeout(this._pongTimeout)
      this._pongTimeout = null
    }
  }

  /**
   * 发送 ping
   */
  _sendPing() {
    if (!this._isConnected) return
    
    this._lastPingId++
    const pingId = this._lastPingId
    
    this.send({
      type: 'client.ping',
      timestamp: Date.now(),
      payload: { id: pingId },
    })
    
    // 设置超时检测
    this._pongTimeout = setTimeout(() => {
      console.warn('[WS] Pong timeout, connection may be dead')
      // 强制重连
      this.ws.close()
    }, this.heartbeatTimeout)
  }

  /**
   * 处理 pong 响应
   */
  _handlePong(message) {
    if (this._pongTimeout) {
      clearTimeout(this._pongTimeout)
      this._pongTimeout = null
    }
    // pong 收到，连接正常
  }

  /**
   * 生成客户端 ID
   */
  _generateClientId() {
    return `web3d_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
  }
}

export { WS_STATE, PROTOCOL_VERSION }
