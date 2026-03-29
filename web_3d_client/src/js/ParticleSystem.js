/**
 * 粒子特效系统
 * 
 * 功能:
 * - 吃子爆炸效果
 * - 移动轨迹效果
 * - 将军警告效果
 */

import * as THREE from 'three'

export class ParticleSystem {
  constructor(scene) {
    this.scene = scene
    this.particles = []
    this.maxParticles = 100
  }

  /**
   * 创建吃子爆炸效果
   * 
   * @param {Object} position - 位置 {x, y, z}
   * @param {string} color - 颜色 (hex)
   */
  createExplosion(position, color = 0xffaa00) {
    const particleCount = 20
    const geometry = new THREE.BufferGeometry()
    const positions = new Float32Array(particleCount * 3)
    const velocities = []
    const lifetimes = []

    for (let i = 0; i < particleCount; i++) {
      positions[i * 3] = position.x
      positions[i * 3 + 1] = position.y + 0.2
      positions[i * 3 + 2] = position.z

      // 随机速度
      const angle = Math.random() * Math.PI * 2
      const speed = 0.5 + Math.random() * 1.5
      const upSpeed = 1 + Math.random() * 2
      velocities.push({
        x: Math.cos(angle) * speed,
        y: upSpeed,
        z: Math.sin(angle) * speed,
      })

      lifetimes.push(0.5 + Math.random() * 0.5) // 0.5-1秒生命周期
    }

    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))

    const material = new THREE.PointsMaterial({
      color: color,
      size: 0.15,
      transparent: true,
      opacity: 1,
      blending: THREE.AdditiveBlending,
    })

    const points = new THREE.Points(geometry, material)
    this.scene.add(points)

    this.particles.push({
      mesh: points,
      velocities,
      lifetimes,
      initialLifetimes: [...lifetimes],
      type: 'explosion',
    })

    // 清理旧粒子
    this._cleanupOldParticles()
  }

  /**
   * 创建移动轨迹效果
   * 
   * @param {Object} fromPos - 起始位置
   * @param {Object} toPos - 目标位置
   */
  createTrail(fromPos, toPos) {
    const particleCount = 15
    const geometry = new THREE.BufferGeometry()
    const positions = new Float32Array(particleCount * 3)
    const progress = []

    for (let i = 0; i < particleCount; i++) {
      const t = i / (particleCount - 1)
      positions[i * 3] = fromPos.x + (toPos.x - fromPos.x) * t
      positions[i * 3 + 1] = fromPos.y + 0.3
      positions[i * 3 + 2] = fromPos.z + (toPos.z - fromPos.z) * t
      progress.push(t)
    }

    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))

    const material = new THREE.PointsMaterial({
      color: 0x88ccff,
      size: 0.1,
      transparent: true,
      opacity: 0.6,
      blending: THREE.AdditiveBlending,
    })

    const points = new THREE.Points(geometry, material)
    this.scene.add(points)

    this.particles.push({
      mesh: points,
      progress,
      lifetimes: new Array(particleCount).fill(0.8),
      initialLifetimes: new Array(particleCount).fill(0.8),
      type: 'trail',
    })

    this._cleanupOldParticles()
  }

  /**
   * 创建将军警告效果
   * 
   * @param {Object} position - 将/帅位置
   */
  createCheckWarning(position) {
    // 红色光环上升效果
    const particleCount = 30
    const geometry = new THREE.BufferGeometry()
    const positions = new Float32Array(particleCount * 3)
    const angles = []
    const radii = []
    const speeds = []
    const lifetimes = []

    for (let i = 0; i < particleCount; i++) {
      const angle = (i / particleCount) * Math.PI * 2
      const radius = 0.5 + Math.random() * 0.3
      
      positions[i * 3] = position.x + Math.cos(angle) * radius
      positions[i * 3 + 1] = position.y + 0.1
      positions[i * 3 + 2] = position.z + Math.sin(angle) * radius

      angles.push(angle)
      radii.push(radius)
      speeds.push(0.5 + Math.random() * 0.5)
      lifetimes.push(1.5) // 1.5秒生命周期
    }

    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))

    const material = new THREE.PointsMaterial({
      color: 0xff3333,
      size: 0.12,
      transparent: true,
      opacity: 0.8,
      blending: THREE.AdditiveBlending,
    })

    const points = new THREE.Points(geometry, material)
    this.scene.add(points)

    this.particles.push({
      mesh: points,
      angles,
      radii,
      speeds,
      lifetimes,
      initialLifetimes: [...lifetimes],
      type: 'check',
    })

    this._cleanupOldParticles()
  }

  /**
   * 更新所有粒子
   * 
   * @param {number} deltaTime - 时间增量(秒)
   */
  update(deltaTime) {
    for (let i = this.particles.length - 1; i >= 0; i--) {
      const p = this.particles[i]
      const positions = p.mesh.geometry.attributes.position.array
      let allDead = true

      if (p.type === 'explosion') {
        for (let j = 0; j < p.velocities.length; j++) {
          if (p.lifetimes[j] > 0) {
            p.lifetimes[j] -= deltaTime
            
            // 更新位置
            positions[j * 3] += p.velocities[j].x * deltaTime
            positions[j * 3 + 1] += p.velocities[j].y * deltaTime
            positions[j * 3 + 2] += p.velocities[j].z * deltaTime
            
            // 重力
            p.velocities[j].y -= 3 * deltaTime
            
            allDead = false
          } else {
            // 隐藏已死亡的粒子
            positions[j * 3 + 1] = -1000
          }
        }
      } else if (p.type === 'trail') {
        for (let j = 0; j < p.lifetimes.length; j++) {
          if (p.lifetimes[j] > 0) {
            p.lifetimes[j] -= deltaTime
            allDead = false
          } else {
            positions[j * 3 + 1] = -1000
          }
        }
        
        // 更新透明度
        const opacity = Math.max(0, Math.min(1, Math.min(...p.lifetimes) / 0.3))
        p.mesh.material.opacity = opacity * 0.6
        
      } else if (p.type === 'check') {
        for (let j = 0; j < p.lifetimes.length; j++) {
          if (p.lifetimes[j] > 0) {
            p.lifetimes[j] -= deltaTime
            
            // 螺旋上升
            const t = 1 - p.lifetimes[j] / p.initialLifetimes[j]
            const newAngle = p.angles[j] + t * Math.PI * 2
            const newRadius = p.radii[j] * (1 + t * 0.5)
            const newY = 0.1 + t * 2
            
            positions[j * 3] = positions[j * 3] + Math.cos(newAngle) * newRadius * 0.01
            positions[j * 3 + 1] = newY
            positions[j * 3 + 2] = positions[j * 3 + 2] + Math.sin(newAngle) * newRadius * 0.01
            
            allDead = false
          } else {
            positions[j * 3 + 1] = -1000
          }
        }
        
        // 更新透明度
        const minLife = Math.min(...p.lifetimes)
        p.mesh.material.opacity = Math.max(0, minLife / 0.5) * 0.8
      }

      p.mesh.geometry.attributes.position.needsUpdate = true

      if (allDead) {
        this.scene.remove(p.mesh)
        p.mesh.geometry.dispose()
        p.mesh.material.dispose()
        this.particles.splice(i, 1)
      }
    }
  }

  /**
   * 清理旧粒子 (限制最大数量)
   */
  _cleanupOldParticles() {
    while (this.particles.length > this.maxParticles) {
      const p = this.particles.shift()
      this.scene.remove(p.mesh)
      p.mesh.geometry.dispose()
      p.mesh.material.dispose()
    }
  }

  /**
   * 清除所有粒子
   */
  clear() {
    this.particles.forEach(p => {
      this.scene.remove(p.mesh)
      p.mesh.geometry.dispose()
      p.mesh.material.dispose()
    })
    this.particles = []
  }
}
