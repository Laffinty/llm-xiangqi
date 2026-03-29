/**
 * 移动动画管理器
 * 
 * 功能:
 * - 棋子移动动画 (贝塞尔曲线)
 * - 棋子被吃动画 (淡出+下沉)
 * - 将军警告动画 (闪烁)
 * - 动画队列管理
 */

// 缓动函数
const EASING = {
  linear: t => t,
  easeInQuad: t => t * t,
  easeOutQuad: t => t * (2 - t),
  easeInOutQuad: t => t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t,
  easeOutCubic: t => 1 - Math.pow(1 - t, 3),
  easeOutBounce: t => {
    const n1 = 7.5625
    const d1 = 2.75
    if (t < 1 / d1) {
      return n1 * t * t
    } else if (t < 2 / d1) {
      return n1 * (t -= 1.5 / d1) * t + 0.75
    } else if (t < 2.5 / d1) {
      return n1 * (t -= 2.25 / d1) * t + 0.9375
    } else {
      return n1 * (t -= 2.625 / d1) * t + 0.984375
    }
  },
}

export class MoveAnimator {
  constructor() {
    // 活跃的动画
    this._activeAnimations = new Map()
    // 动画 ID 计数器
    this._animationId = 0
  }

  /**
   * 移动棋子动画
   * 
   * @param {THREE.Object3D} piece - 棋子对象
   * @param {Object} targetPos - 目标位置 {x, y, z}
   * @param {Object} options - 动画选项
   * @returns {Promise} 动画完成 Promise
   */
  animateMove(piece, targetPos, options = {}) {
    const {
      duration = 0.5,
      easing = 'easeOutCubic',
      arcHeight = 0.5, // 弧线高度
      onComplete = null,
    } = options

    const startPos = piece.position.clone()
    const id = this._animationId++

    return new Promise((resolve) => {
      const startTime = performance.now()
      const easeFunc = EASING[easing] || EASING.easeOutCubic

      const animate = (time) => {
        const elapsed = (time - startTime) / 1000
        const progress = Math.min(elapsed / duration, 1)
        const eased = easeFunc(progress)

        // 水平插值
        piece.position.x = startPos.x + (targetPos.x - startPos.x) * eased
        piece.position.z = startPos.z + (targetPos.z - startPos.z) * eased

        // 垂直弧线 (先上升后下降)
        if (arcHeight > 0) {
          const arcProgress = Math.sin(progress * Math.PI)
          piece.position.y = startPos.y + arcProgress * arcHeight
        } else {
          piece.position.y = startPos.y + (targetPos.y - startPos.y) * eased
        }

        if (progress < 1) {
          this._activeAnimations.set(id, requestAnimationFrame(animate))
        } else {
          // 确保最终位置精确
          piece.position.set(targetPos.x, targetPos.y, targetPos.z)
          this._activeAnimations.delete(id)
          if (onComplete) onComplete()
          resolve()
        }
      }

      this._activeAnimations.set(id, requestAnimationFrame(animate))
    })
  }

  /**
   * 棋子被吃动画
   * 
   * @param {THREE.Object3D} piece - 棋子对象
   * @param {Object} options - 动画选项
   * @returns {Promise} 动画完成 Promise
   */
  animateCapture(piece, options = {}) {
    const {
      duration = 0.4,
      sinkDepth = 2, // 下沉深度
      onComplete = null,
    } = options

    const startY = piece.position.y
    const startScale = piece.scale.x
    const id = this._animationId++

    return new Promise((resolve) => {
      const startTime = performance.now()

      const animate = (time) => {
        const elapsed = (time - startTime) / 1000
        const progress = Math.min(elapsed / duration, 1)

        // 下沉
        piece.position.y = startY - progress * sinkDepth

        // 缩小
        const scale = startScale * (1 - progress)
        piece.scale.setScalar(scale)

        // 透明度淡出 (如果材质支持)
        piece.traverse((child) => {
          if (child.material && child.material.transparent !== undefined) {
            child.material.transparent = true
            child.material.opacity = 1 - progress
          }
        })

        if (progress < 1) {
          this._activeAnimations.set(id, requestAnimationFrame(animate))
        } else {
          this._activeAnimations.delete(id)
          if (onComplete) onComplete()
          resolve()
        }
      }

      this._activeAnimations.set(id, requestAnimationFrame(animate))
    })
  }

  /**
   * 棋子出现动画
   * 
   * @param {THREE.Object3D} piece - 棋子对象
   * @param {Object} options - 动画选项
   * @returns {Promise} 动画完成 Promise
   */
  animateAppear(piece, options = {}) {
    const {
      duration = 0.3,
      onComplete = null,
    } = options

    const targetScale = 1
    piece.scale.setScalar(0)
    const id = this._animationId++

    return new Promise((resolve) => {
      const startTime = performance.now()

      const animate = (time) => {
        const elapsed = (time - startTime) / 1000
        const progress = Math.min(elapsed / duration, 1)

        // 弹性放大
        const scale = targetScale * EASING.easeOutBounce(progress)
        piece.scale.setScalar(scale)

        if (progress < 1) {
          this._activeAnimations.set(id, requestAnimationFrame(animate))
        } else {
          piece.scale.setScalar(targetScale)
          this._activeAnimations.delete(id)
          if (onComplete) onComplete()
          resolve()
        }
      }

      this._activeAnimations.set(id, requestAnimationFrame(animate))
    })
  }

  /**
   * 选中闪烁动画
   * 
   * @param {THREE.Mesh} highlightMesh - 高亮网格
   * @returns {number} 动画 ID (用于停止)
   */
  animateSelection(highlightMesh) {
    const id = this._animationId++

    const animate = (time) => {
      if (!highlightMesh.parent) return

      const t = time / 1000
      // 脉冲效果
      const scale = 1 + Math.sin(t * 8) * 0.1
      const opacity = 0.6 + Math.sin(t * 8) * 0.2

      highlightMesh.scale.setScalar(scale)
      highlightMesh.material.opacity = opacity

      this._activeAnimations.set(id, requestAnimationFrame(animate))
    }

    this._activeAnimations.set(id, requestAnimationFrame(animate))
    return id
  }

  /**
   * 停止指定动画
   * 
   * @param {number} id - 动画 ID
   */
  stopAnimation(id) {
    const frameId = this._activeAnimations.get(id)
    if (frameId) {
      cancelAnimationFrame(frameId)
      this._activeAnimations.delete(id)
    }
  }

  /**
   * 停止所有动画
   */
  stopAll() {
    this._activeAnimations.forEach((frameId) => {
      cancelAnimationFrame(frameId)
    })
    this._activeAnimations.clear()
  }

  /**
   * 检查是否有活跃动画
   */
  hasActiveAnimations() {
    return this._activeAnimations.size > 0
  }
}

export { EASING }
