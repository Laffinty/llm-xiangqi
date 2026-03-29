/**
 * 音效管理器
 * 
 * 功能:
 * - 走子音效
 * - 吃子音效
 * - 将军音效
 * - 游戏结束音效
 * - 音量控制
 */

// 使用 Web Audio API 生成简单音效
export class SoundManager {
  constructor() {
    this.ctx = null
    this.enabled = true
    this.volume = 0.5
    this.sounds = new Map()
  }

  /**
   * 初始化音频上下文
   */
  init() {
    try {
      this.ctx = new (window.AudioContext || window.webkitAudioContext)()
      console.info('[Sound] Audio context initialized')
    } catch (e) {
      console.warn('[Sound] Web Audio API not supported')
      this.enabled = false
    }
  }

  /**
   * 播放走子音效
   */
  playMove() {
    if (!this.enabled || !this.ctx) return

    // 短促的"咔哒"声
    const osc = this.ctx.createOscillator()
    const gain = this.ctx.createGain()

    osc.type = 'square'
    osc.frequency.setValueAtTime(800, this.ctx.currentTime)
    osc.frequency.exponentialRampToValueAtTime(400, this.ctx.currentTime + 0.05)

    gain.gain.setValueAtTime(this.volume * 0.3, this.ctx.currentTime)
    gain.gain.exponentialRampToValueAtTime(0.01, this.ctx.currentTime + 0.05)

    osc.connect(gain)
    gain.connect(this.ctx.destination)

    osc.start()
    osc.stop(this.ctx.currentTime + 0.05)
  }

  /**
   * 播放吃子音效
   */
  playCapture() {
    if (!this.enabled || !this.ctx) return

    // 低沉的"砰"声
    const osc = this.ctx.createOscillator()
    const gain = this.ctx.createGain()

    osc.type = 'sawtooth'
    osc.frequency.setValueAtTime(200, this.ctx.currentTime)
    osc.frequency.exponentialRampToValueAtTime(100, this.ctx.currentTime + 0.15)

    gain.gain.setValueAtTime(this.volume * 0.5, this.ctx.currentTime)
    gain.gain.exponentialRampToValueAtTime(0.01, this.ctx.currentTime + 0.15)

    osc.connect(gain)
    gain.connect(this.ctx.destination)

    osc.start()
    osc.stop(this.ctx.currentTime + 0.15)
  }

  /**
   * 播放将军音效
   */
  playCheck() {
    if (!this.enabled || !this.ctx) return

    // 警告音
    const osc = this.ctx.createOscillator()
    const gain = this.ctx.createGain()

    osc.type = 'sine'
    osc.frequency.setValueAtTime(600, this.ctx.currentTime)
    osc.frequency.setValueAtTime(800, this.ctx.currentTime + 0.1)
    osc.frequency.setValueAtTime(600, this.ctx.currentTime + 0.2)

    gain.gain.setValueAtTime(this.volume * 0.4, this.ctx.currentTime)
    gain.gain.setValueAtTime(this.volume * 0.4, this.ctx.currentTime + 0.1)
    gain.gain.exponentialRampToValueAtTime(0.01, this.ctx.currentTime + 0.3)

    osc.connect(gain)
    gain.connect(this.ctx.destination)

    osc.start()
    osc.stop(this.ctx.currentTime + 0.3)
  }

  /**
   * 播放游戏结束音效
   */
  playGameOver(winner) {
    if (!this.enabled || !this.ctx) return

    const osc = this.ctx.createOscillator()
    const gain = this.ctx.createGain()

    osc.type = 'sine'
    
    // 胜利音效 (上行音阶)
    if (winner) {
      const now = this.ctx.currentTime
      osc.frequency.setValueAtTime(400, now)
      osc.frequency.setValueAtTime(600, now + 0.1)
      osc.frequency.setValueAtTime(800, now + 0.2)
      gain.gain.setValueAtTime(this.volume * 0.3, now)
      gain.gain.linearRampToValueAtTime(0.01, now + 0.5)
      osc.start()
      osc.stop(now + 0.5)
    } else {
      // 平局音效
      const now = this.ctx.currentTime
      osc.frequency.setValueAtTime(500, now)
      gain.gain.setValueAtTime(this.volume * 0.3, now)
      gain.gain.exponentialRampToValueAtTime(0.01, now + 0.3)
      osc.start()
      osc.stop(now + 0.3)
    }

    osc.connect(gain)
    gain.connect(this.ctx.destination)
  }

  /**
   * 设置音量
   */
  setVolume(vol) {
    this.volume = Math.max(0, Math.min(1, vol))
  }

  /**
   * 启用/禁用音效
   */
  setEnabled(enabled) {
    this.enabled = enabled
    if (enabled && !this.ctx) {
      this.init()
    }
  }

  /**
   * 切换静音
   */
  toggle() {
    this.enabled = !this.enabled
    if (this.enabled && !this.ctx) {
      this.init()
    }
    return this.enabled
  }
}
