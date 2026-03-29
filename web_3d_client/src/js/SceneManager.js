/**
 * 3D 场景管理器
 * 
 * 功能:
 * - WebGPU/WebGL 2.0 自动降级渲染器初始化
 * - 场景、相机、光照管理
 * - 棋盘和棋子渲染
 * - 选中/移动高亮特效
 */

import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { MoveAnimator } from './MoveAnimator.js'
import { ParticleSystem } from './ParticleSystem.js'
import { SoundManager } from './SoundManager.js'

// 渲染器类型
const RENDERER_TYPE = {
  WEBGPU: 'webgpu',
  WEBGL2: 'webgl2',
}

// 棋盘配置
const BOARD_CONFIG = {
  width: 9,      // 9 列
  height: 10,    // 10 行
  cellSize: 1.0,
  colors: {
    background: 0x0a0a0f,  // 深邃墨黑
    board: 0xe8d4b8,       // 明亮木纹色，高对比
    line: 0x1a0f0a,        // 深褐色，强对比线条
    river: 0x2d1f16,       // 中褐色，清晰可辨
  },
}

// 棋子配置
const PIECE_CONFIG = {
  radius: 0.38,
  height: 0.4,
  colors: {
    red: {
      body: 0xfffef8,   // 棋子本体 - 纯白，高对比
      text: 0xcc0000,   // 文字颜色 - 鲜红，醒目
      base: 0xd4a76a,   // 底座 - 金棕色
    },
    black: {
      body: 0xfffef8,   // 棋子本体 - 纯白，高对比
      text: 0x0a0a0a,   // 文字颜色 - 纯黑，醒目
      base: 0x6b5344,   // 底座 - 深棕灰
    },
  },
}

export class SceneManager {
  constructor(canvas, options = {}) {
    this.canvas = canvas
    this.options = {
      shadowMapSize: options.shadowMapSize || 2048,
      cameraPosition: options.cameraPosition || [8, 12, 12],
      lightFollowsCamera: options.lightFollowsCamera || false,  // 光源是否跟随相机
      ...options,
    }
    
    // 核心组件
    this.renderer = null
    this.scene = null
    this.camera = null
    this.controls = null
    
    // 渲染器类型
    this.rendererType = null
    
    // 对象引用
    this.boardGroup = null
    this.piecesGroup = null
    this.effectsGroup = null
    
    // 棋子对象映射 (iccs -> mesh)
    this.pieces = new Map()
    
    // 动画管理器
    this.animator = new MoveAnimator()
    
    // 粒子系统 (初始化后创建)
    this.particles = null
    
    // 音效管理器
    this.sounds = new SoundManager()
    
    // 选中状态
    this.selectedPiece = null
    this._selectionHighlight = null
    this._selectionAnimationId = null
    
    // 动画循环
    this._animationId = null
    this._isRunning = false
    this._lastTime = 0
  }

  /**
   * 初始化场景
   */
  async init() {
    // 初始化渲染器 (WebGPU -> WebGL 2.0)
    await this._initRenderer()
    
    // 创建场景
    this.scene = new THREE.Scene()
    this.scene.background = new THREE.Color(BOARD_CONFIG.colors.background)
    
    // 创建相机
    this._initCamera()
    
    // 创建控制器
    this._initControls()
    
    // 设置光照
    this._initLighting()
    
    // 创建场景对象容器
    this._initObjectGroups()
    
    // 创建棋盘
    this._createBoard()
    
    // 初始化粒子系统
    this.particles = new ParticleSystem(this.scene)
    
    // 初始化音效
    this.sounds.init()
    
    // 开始渲染循环
    this._startRenderLoop()
    
    console.info('[Scene] Initialized with renderer:', this.rendererType)
  }

  /**
   * 初始化渲染器 (WebGL 2.0)
   * 
   * 注: WebGPU 支持需要特殊配置，当前使用 WebGL 2.0 作为稳定方案
   */
  async _initRenderer() {
    // 检查 WebGL 2.0 支持
    const gl = this.canvas.getContext('webgl2')
    if (!gl) {
      throw new Error('WebGL 2.0 not supported by your browser')
    }
    
    // 创建 WebGL 2.0 渲染器
    this.renderer = new THREE.WebGLRenderer({
      canvas: this.canvas,
      antialias: true,
      alpha: false,
      powerPreference: 'high-performance',
    })
    this.rendererType = RENDERER_TYPE.WEBGL2
    console.info('[Scene] Using WebGL 2.0 renderer')
    
    // 配置渲染器
    this.renderer.setSize(this.canvas.clientWidth, this.canvas.clientHeight)
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    
    // 阴影配置
    this.renderer.shadowMap.enabled = true
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap
    this.renderer.shadowMap.autoUpdate = true
    
    // 处理窗口大小变化
    window.addEventListener('resize', () => this._handleResize())
  }

  /**
   * 初始化相机
   */
  _initCamera() {
    const aspect = this.canvas.clientWidth / this.canvas.clientHeight
    this.camera = new THREE.PerspectiveCamera(45, aspect, 0.1, 100)
    
    const [x, y, z] = this.options.cameraPosition
    this.camera.position.set(x, y, z)
    this.camera.lookAt(0, 0, 0)
  }

  /**
   * 初始化控制器
   */
  _initControls() {
    this.controls = new OrbitControls(this.camera, this.canvas)
    this.controls.enableDamping = true
    this.controls.dampingFactor = 0.05
    this.controls.maxPolarAngle = Math.PI / 2.2  // 限制垂直角度
    this.controls.minDistance = 5
    this.controls.maxDistance = 30
    this.controls.target.set(0, 0, 0)
  }

  /**
   * 初始化光照
   * 光源固定在空间坐标，不随相机或棋盘移动
   */
  _initLighting() {
    // 环境光 - 暖白色，提供基础照明
    const ambient = new THREE.AmbientLight(0xfff8e7, 0.6)
    this.scene.add(ambient)
    
    // 半球光 - 模拟天空和地面的自然光照，提供更均匀的照明
    const hemiLight = new THREE.HemisphereLight(0xffffff, 0xd4b896, 0.5)
    hemiLight.position.set(0, 20, 0)
    this.scene.add(hemiLight)
    
    // 主光源 (产生阴影) - 固定在空间坐标，使用 DirectionalLight 获得平行光效果
    const mainLight = new THREE.DirectionalLight(0xfff8e7, 1.0)
    // 光源位置固定在世界空间，与棋盘和相机无关
    mainLight.position.set(8, 12, 8)
    mainLight.target.position.set(0, 0, 0)
    mainLight.castShadow = true
    
    // 阴影配置 - 优化参数使阴影更清晰
    mainLight.shadow.mapSize.width = this.options.shadowMapSize
    mainLight.shadow.mapSize.height = this.options.shadowMapSize
    mainLight.shadow.camera.near = 0.5
    mainLight.shadow.camera.far = 50
    mainLight.shadow.camera.left = -8
    mainLight.shadow.camera.right = 8
    mainLight.shadow.camera.top = 8
    mainLight.shadow.camera.bottom = -8
    mainLight.shadow.bias = -0.0001
    mainLight.shadow.radius = 2
    
    this.mainLight = mainLight
    // 将光源直接添加到场景，确保它是世界坐标
    this.scene.add(mainLight)
    this.scene.add(mainLight.target)
    
    // 补光 - 从另一侧提供柔和照明
    const fillLight = new THREE.DirectionalLight(0xfff8e7, 0.4)
    fillLight.position.set(-5, 8, -5)
    this.scene.add(fillLight)
  }

  /**
   * 初始化对象分组
   */
  _initObjectGroups() {
    this.boardGroup = new THREE.Group()
    this.boardGroup.name = 'board'
    this.scene.add(this.boardGroup)
    
    this.piecesGroup = new THREE.Group()
    this.piecesGroup.name = 'pieces'
    this.scene.add(this.piecesGroup)
    
    this.effectsGroup = new THREE.Group()
    this.effectsGroup.name = 'effects'
    this.scene.add(this.effectsGroup)
  }

  /**
   * 创建程序化棋盘
   */
  _createBoard() {
    const { width, height, cellSize, colors } = BOARD_CONFIG
    
    // 棋盘底座（整个棋盘底色）
    const boardWidth = width * cellSize + 0.5
    const boardHeight = height * cellSize + 0.5
    const boardThickness = 0.3
    
    const baseGeometry = new THREE.BoxGeometry(boardWidth, boardThickness, boardHeight)
    const baseMaterial = new THREE.MeshStandardMaterial({
      color: colors.board,
      roughness: 0.7,
      metalness: 0.1,
    })
    const base = new THREE.Mesh(baseGeometry, baseMaterial)
    base.position.y = -boardThickness / 2
    base.receiveShadow = true
    this.boardGroup.add(base)
    
    // 创建河界纯色区域（row 4 和 row 5 之间）
    this._createRiverArea()
    
    // 创建棋格线
    this._createGridLines()
    
    // 楚河汉界文字
    this._createRiverLabels()
  }

  /**
   * 创建河界区域
   * 
   * 标准象棋棋盘：
   * - 河界区域与棋盘同色
   * - 宽度严格对齐a-i列
   */
  _createRiverArea() {
    const { cellSize, colors } = BOARD_CONFIG
    
    // 河界区域宽度：从a列(-4)到i列(+4)，共8格
    const riverWidth = 8 * cellSize
    const riverHeight = cellSize  // 一格高度
    
    // 河界平面（与棋盘同色）
    const riverGeometry = new THREE.PlaneGeometry(riverWidth, riverHeight)
    const riverMaterial = new THREE.MeshStandardMaterial({
      color: colors.board,  // 与棋盘同色
      roughness: 0.8,
      metalness: 0.05,
    })
    
    const river = new THREE.Mesh(riverGeometry, riverMaterial)
    river.rotation.x = -Math.PI / 2
    river.position.set(0, 0.002, 0)
    river.receiveShadow = true
    
    this.boardGroup.add(river)
  }

  /**
   * 创建棋格线
   * 
   * 标准象棋棋盘：
   * - 横线：全部绘制（包括row 4和row 5作为河界边界）
   * - 竖线：a列(col 0) 和 i列(col 8) 贯穿河界，其他列在河界处断开
   * 
   * 坐标系：row 0 -> z = -4.5（远离用户，黑方底线）
   *        row 9 -> z = 4.5（靠近用户，红方底线）
   */
  _createGridLines() {
    const { width, height, cellSize, colors } = BOARD_CONFIG
    const lineMaterial = new THREE.LineBasicMaterial({ color: colors.line, linewidth: 2 })
    
    const halfWidth = (width - 1) * cellSize / 2  // 4
    const halfHeight = (height - 1) * cellSize / 2  // 4.5
    
    // 河界边界z坐标
    const riverTopZ = -halfHeight + 4 * cellSize    // row 4: z = -0.5
    const riverBottomZ = -halfHeight + 5 * cellSize // row 5: z = 0.5
    
    // 横线：row 0-9（全部绘制，包括row 4和row 5作为河界上下边界）
    for (let row = 0; row < height; row++) {
      const z = -halfHeight + row * cellSize
      const points = [
        new THREE.Vector3(-halfWidth, 0.005, z),
        new THREE.Vector3(halfWidth, 0.005, z),
      ]
      const geometry = new THREE.BufferGeometry().setFromPoints(points)
      this.boardGroup.add(new THREE.Line(geometry, lineMaterial))
    }
    
    // 竖线：col 0-8 (a-i列)
    for (let col = 0; col < width; col++) {
      const x = -halfWidth + col * cellSize
      
      if (col === 0 || col === 8) {
        // a列(col 0) 和 i列(col 8)：贯穿河界
        const points = [
          new THREE.Vector3(x, 0.005, -halfHeight),
          new THREE.Vector3(x, 0.005, halfHeight),
        ]
        const geometry = new THREE.BufferGeometry().setFromPoints(points)
        this.boardGroup.add(new THREE.Line(geometry, lineMaterial))
      } else {
        // b-h列：在河界处断开，画两段
        // 上半段：从黑方底线到河界上沿
        const pointsTop = [
          new THREE.Vector3(x, 0.005, -halfHeight),
          new THREE.Vector3(x, 0.005, riverTopZ),
        ]
        const geometryTop = new THREE.BufferGeometry().setFromPoints(pointsTop)
        this.boardGroup.add(new THREE.Line(geometryTop, lineMaterial))
        
        // 下半段：从河界下沿到红方底线
        const pointsBottom = [
          new THREE.Vector3(x, 0.005, riverBottomZ),
          new THREE.Vector3(x, 0.005, halfHeight),
        ]
        const geometryBottom = new THREE.BufferGeometry().setFromPoints(pointsBottom)
        this.boardGroup.add(new THREE.Line(geometryBottom, lineMaterial))
      }
    }
    
    // 九宫格斜线
    this._createPalaceLines(halfWidth, halfHeight, cellSize, lineMaterial)
  }

  /**
   * 创建九宫格斜线
   * 
   * 标准规范：
   * - 黑方九宫：row 0-2, col 3-5（底线起3行，中间3列 d-e-f），棋盘上方（z < 0）
   * - 红方九宫：row 7-9, col 3-5（底线起3行，中间3列 d-e-f），棋盘下方（z > 0）
   * 
   * 坐标系：row 0 -> z = -4.5（远离用户，黑方底线）
   *        row 9 -> z = 4.5（靠近用户，红方底线）
   */
  _createPalaceLines(halfWidth, halfHeight, cellSize, material) {
    // 列索引：3=d, 4=e, 5=f
    const leftCol = -halfWidth + 3 * cellSize   // d 列
    const midCol = -halfWidth + 4 * cellSize    // e 列（中间）
    const rightCol = -halfWidth + 5 * cellSize  // f 列
    
    // 黑方九宫（棋盘上方，row 0-2，z < 0）
    // row 0 -> z = -4.5, row 2 -> z = -2.5
    const blackTopZ = -halfHeight              // row 0（远离用户）
    const blackBottomZ = -halfHeight + 2 * cellSize  // row 2
    
    // 黑方九宫四角
    const blackTopLeft = new THREE.Vector3(leftCol, 0.005, blackTopZ)
    const blackTopRight = new THREE.Vector3(rightCol, 0.005, blackTopZ)
    const blackBottomLeft = new THREE.Vector3(leftCol, 0.005, blackBottomZ)
    const blackBottomRight = new THREE.Vector3(rightCol, 0.005, blackBottomZ)
    
    // 黑方对角线（连接四角）
    const diag1 = new THREE.BufferGeometry().setFromPoints([blackTopLeft, blackBottomRight])
    const diag2 = new THREE.BufferGeometry().setFromPoints([blackTopRight, blackBottomLeft])
    this.boardGroup.add(new THREE.Line(diag1, material))
    this.boardGroup.add(new THREE.Line(diag2, material))
    
    // 红方九宫（棋盘下方，row 7-9，z > 0）
    // row 7 -> z = 2.5, row 9 -> z = 4.5
    const redTopZ = halfHeight - 2 * cellSize   // row 7
    const redBottomZ = halfHeight               // row 9（靠近用户）
    
    // 红方九宫四角
    const redTopLeft = new THREE.Vector3(leftCol, 0.005, redTopZ)
    const redTopRight = new THREE.Vector3(rightCol, 0.005, redTopZ)
    const redBottomLeft = new THREE.Vector3(leftCol, 0.005, redBottomZ)
    const redBottomRight = new THREE.Vector3(rightCol, 0.005, redBottomZ)
    
    // 红方对角线（连接四角）
    const diag3 = new THREE.BufferGeometry().setFromPoints([redTopLeft, redBottomRight])
    const diag4 = new THREE.BufferGeometry().setFromPoints([redTopRight, redBottomLeft])
    this.boardGroup.add(new THREE.Line(diag3, material))
    this.boardGroup.add(new THREE.Line(diag4, material))
  }

  /**
   * 创建楚河汉界文字
   * 
   * 标准规范：
   * - "楚河"和"汉界"位于同一行，水平对齐
   * - 字体垂直居中，字号与棋面字体一致（80px）
   * - 传统书法风格，深棕色文字
   */
  _createRiverLabels() {
    const { cellSize, colors } = BOARD_CONFIG
    
    // 创建包含"楚河"和"汉界"的同一行文字
    const canvas = document.createElement('canvas')
    canvas.width = 512
    canvas.height = 128
    const ctx = canvas.getContext('2d')
    
    // 透明背景
    ctx.clearRect(0, 0, 512, 128)
    
    // 设置字体（楷书风格，字号与棋面一致：80px）
    ctx.font = 'bold 80px "KaiTi", "STKaiti", "楷体", "SimSun", serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    
    // 绘制"楚河"（左侧）- 使用配置颜色（深褐色）
    const riverColorHex = colors.river.toString(16).padStart(6, '0')
    ctx.fillStyle = '#' + riverColorHex
    console.log('[Scene] River label color:', ctx.fillStyle, 'from', colors.river)
    ctx.fillText('楚河', 140, 64)
    
    // 绘制"汉界"（右侧）
    ctx.fillText('汉界', 380, 64)
    
    const texture = new THREE.CanvasTexture(canvas)
    texture.minFilter = THREE.LinearFilter
    texture.magFilter = THREE.LinearFilter
    
    const material = new THREE.MeshBasicMaterial({ 
      map: texture, 
      transparent: true,
      opacity: 1.0,
      side: THREE.DoubleSide
    })
    
    // 平面尺寸适配文字
    const geometry = new THREE.PlaneGeometry(3.2, 0.8)
    const mesh = new THREE.Mesh(geometry, material)
    mesh.rotation.x = -Math.PI / 2
    // 垂直居中于河界区域（z = 0）
    mesh.position.set(0, 0.008, 0)
    
    this.boardGroup.add(mesh)
  }

  /**
   * 创建程序化棋子
   */
  createPiece(pieceChar, iccs) {
    const color = pieceChar === pieceChar.toUpperCase() ? 'red' : 'black'
    const colors = PIECE_CONFIG.colors[color]
    const config = PIECE_CONFIG
    
    const group = new THREE.Group()
    
    // 底座
    const baseGeometry = new THREE.CylinderGeometry(config.radius, config.radius + 0.02, 0.08, 32)
    const baseMaterial = new THREE.MeshLambertMaterial({
      color: colors.base,
    })
    const base = new THREE.Mesh(baseGeometry, baseMaterial)
    base.castShadow = true
    base.receiveShadow = true
    group.add(base)
    
    // 主体
    const bodyGeometry = new THREE.CylinderGeometry(config.radius - 0.02, config.radius, config.height - 0.1, 32)
    const bodyMaterial = new THREE.MeshLambertMaterial({
      color: colors.body,
    })
    const body = new THREE.Mesh(bodyGeometry, bodyMaterial)
    body.position.y = config.height / 2
    body.castShadow = true
    body.receiveShadow = true
    group.add(body)
    
    // 文字
    const textMesh = this._createPieceText(pieceChar, colors.text)
    textMesh.position.y = config.height + 0.01
    group.add(textMesh)
    
    // 设置位置
    const pos = this._iccsToWorld(iccs)
    group.position.set(pos.x, pos.y, pos.z)
    
    // 黑方棋子旋转180度，使其朝向红方（标准规范）
    if (color === 'black') {
      group.rotation.y = Math.PI
    }
    
    // 存储引用
    group.userData = { iccs, piece: pieceChar }
    this.pieces.set(iccs, group)
    this.piecesGroup.add(group)
    
    // 播放出现动画
    this.animator.animateAppear(group)
    
    return group
  }

  /**
   * 创建棋子文字
   */
  _createPieceText(char, color) {
    const canvas = document.createElement('canvas')
    canvas.width = 128
    canvas.height = 128
    const ctx = canvas.getContext('2d')
    
    // 透明背景
    ctx.clearRect(0, 0, 128, 128)
    
    // 文字
    ctx.fillStyle = '#' + color.toString(16).padStart(6, '0')
    ctx.font = 'bold 80px "Microsoft YaHei", "SimHei", serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(this._getPieceDisplayChar(char), 64, 64)
    
    const texture = new THREE.CanvasTexture(canvas)
    const material = new THREE.MeshBasicMaterial({
      map: texture,
      transparent: true,
      side: THREE.DoubleSide,
    })
    
    const geometry = new THREE.PlaneGeometry(0.6, 0.6)
    const mesh = new THREE.Mesh(geometry, material)
    mesh.rotation.x = -Math.PI / 2
    
    return mesh
  }

  /**
   * 获取棋子显示字符
   */
  _getPieceDisplayChar(char) {
    const names = {
      'K': '帅', 'A': '仕', 'B': '相', 'N': '傌', 'R': '俥', 'C': '炮', 'P': '兵',
      'k': '将', 'a': '士', 'b': '象', 'n': '马', 'r': '车', 'c': '砲', 'p': '卒',
    }
    return names[char] || char
  }

  /**
   * ICCS 转世界坐标
   * 
   * 棋子底部贴合棋盘表面
   * y = 0.04 (底座厚度的一半 + 微小间隙防止z-fighting)
   * 
   * 坐标系：红方在靠近用户一侧（棋盘下方，z > 0）
   *        黑方在远离用户一侧（棋盘上方，z < 0）
   */
  _iccsToWorld(iccs) {
    const col = iccs[0].toLowerCase()
    const row = parseInt(iccs.slice(1))
    
    const colIndex = col.charCodeAt(0) - 'a'.charCodeAt(0)
    const rowIndex = row
    
    const { cellSize } = BOARD_CONFIG
    
    // 翻转Z轴：row 0（黑方底线）-> z = -4.5（远离用户）
    //         row 9（红方底线）-> z = 4.5（靠近用户）
    return {
      x: (colIndex - 4) * cellSize,
      y: 0.04,  // 棋子底部贴合棋盘表面
      z: (rowIndex - 4.5) * cellSize,
    }
  }

  /**
   * 移动棋子
   * 
   * @param {string} fromIccs - 起始 ICCS 坐标
   * @param {string} toIccs - 目标 ICCS 坐标
   * @param {number} duration - 动画持续时间(秒)
   * @param {boolean} isCapture - 是否是吃子
   * @returns {Promise} 动画完成 Promise
   */
  async movePiece(fromIccs, toIccs, duration = 0.5, isCapture = false) {
    const piece = this.pieces.get(fromIccs)
    if (!piece) {
      console.warn('[Scene] Piece not found at', fromIccs)
      return
    }
    
    // 如果正在移动选中的棋子，取消选中状态
    if (this.selectedPiece === fromIccs) {
      this.deselectPiece()
    }
    
    const fromPos = this._iccsToWorld(fromIccs)
    const targetPos = this._iccsToWorld(toIccs)
    
    // 创建轨迹粒子
    if (this.particles) {
      this.particles.createTrail(fromPos, targetPos)
    }
    
    // 播放移动音效
    if (this.sounds) {
      this.sounds.playMove()
    }
    
    // 目标位置是否有棋子 (被吃)
    const capturedPiece = this.pieces.get(toIccs)
    if (capturedPiece) {
      await this.removePiece(toIccs, duration * 0.8)
      isCapture = true
    }
    
    // 更新映射
    this.pieces.delete(fromIccs)
    this.pieces.set(toIccs, piece)
    piece.userData.iccs = toIccs
    
    // 使用 MoveAnimator 进行动画
    await this.animator.animateMove(piece, targetPos, {
      duration,
      arcHeight: 0.3, // 添加弧线效果
    })
  }

  /**
   * 移除棋子 (被吃)
   * 
   * @param {string} iccs - ICCS 坐标
   * @param {number} duration - 动画持续时间(秒)
   * @returns {Promise} 动画完成 Promise
   */
  async removePiece(iccs, duration = 0.3) {
    const piece = this.pieces.get(iccs)
    if (!piece) return
    
    this.pieces.delete(iccs)
    
    // 获取位置并创建爆炸效果
    const pos = piece.position.clone()
    
    // 播放吃子音效
    if (this.sounds) {
      this.sounds.playCapture()
    }
    
    // 创建爆炸粒子效果
    if (this.particles) {
      const color = piece.userData.piece === piece.userData.piece.toUpperCase() 
        ? 0xff6b6b  // 红方 - 红色
        : 0x4a4a4a  // 黑方 - 深灰色
      this.particles.createExplosion(pos, color)
    }
    
    // 使用 MoveAnimator 进行被吃动画
    await this.animator.animateCapture(piece, { duration })
    
    // 从场景中移除并清理资源
    this.piecesGroup.remove(piece)
    piece.traverse(child => {
      if (child.geometry) child.geometry.dispose()
      if (child.material) {
        if (Array.isArray(child.material)) {
          child.material.forEach(m => m.dispose())
        } else {
          child.material.dispose()
        }
      }
    })
  }

  /**
   * 选中棋子
   * 
   * @param {string} iccs - ICCS 坐标
   */
  selectPiece(iccs) {
    // 如果已选中同一棋子，取消选中
    if (this.selectedPiece === iccs) {
      this.deselectPiece()
      return
    }

    // 取消之前的选中
    this.deselectPiece()

    const piece = this.pieces.get(iccs)
    if (!piece) return

    this.selectedPiece = iccs

    // 创建选中高亮
    this._createSelectionHighlight(iccs)
  }

  /**
   * 取消选中
   */
  deselectPiece() {
    if (this._selectionAnimationId !== null) {
      this.animator.stopAnimation(this._selectionAnimationId)
      this._selectionAnimationId = null
    }

    if (this._selectionHighlight) {
      this.effectsGroup.remove(this._selectionHighlight)
      this._selectionHighlight.geometry.dispose()
      this._selectionHighlight.material.dispose()
      this._selectionHighlight = null
    }

    this.selectedPiece = null
  }

  /**
   * 创建选中高亮
   */
  _createSelectionHighlight(iccs) {
    const pos = this._iccsToWorld(iccs)

    const geometry = new THREE.RingGeometry(0.4, 0.5, 32)
    const material = new THREE.MeshBasicMaterial({
      color: 0xffd700, // 金黄色
      transparent: true,
      opacity: 0.8,
      side: THREE.DoubleSide,
    })

    this._selectionHighlight = new THREE.Mesh(geometry, material)
    this._selectionHighlight.rotation.x = -Math.PI / 2
    this._selectionHighlight.position.set(pos.x, 0.06, pos.z)

    this.effectsGroup.add(this._selectionHighlight)

    // 启动闪烁动画
    this._selectionAnimationId = this.animator.animateSelection(this._selectionHighlight)
  }

  /**
   * 高亮最后走法
   */
  highlightLastMove(fromIccs, toIccs) {
    // 清除旧的高亮
    this.clearHighlights()
    
    // 创建起点和终点标记
    this._createHighlightMarker(fromIccs, 0x00ff00, 'from') // 绿色
    this._createHighlightMarker(toIccs, 0x0088ff, 'to')     // 蓝色
  }

  /**
   * 创建高亮标记
   */
  _createHighlightMarker(iccs, color, type) {
    const pos = this._iccsToWorld(iccs)
    
    const geometry = new THREE.RingGeometry(0.35, 0.45, 32)
    const material = new THREE.MeshBasicMaterial({
      color,
      transparent: true,
      opacity: 0.6,
      side: THREE.DoubleSide,
    })
    
    const marker = new THREE.Mesh(geometry, material)
    marker.rotation.x = -Math.PI / 2
    marker.position.set(pos.x, 0.05, pos.z)
    marker.userData = { type: 'highlight', highlightType: type }
    
    this.effectsGroup.add(marker)
    
    // 呼吸动画
    const animate = () => {
      if (!marker.parent) return
      const time = performance.now() / 1000
      const scale = 1 + Math.sin(time * 3) * 0.1
      marker.scale.setScalar(scale)
      marker.material.opacity = 0.4 + Math.sin(time * 3) * 0.2
      requestAnimationFrame(animate)
    }
    requestAnimationFrame(animate)
  }

  /**
   * 清除高亮
   */
  clearHighlights() {
    const toRemove = []
    this.effectsGroup.traverse(child => {
      if (child.userData.type === 'highlight') {
        toRemove.push(child)
      }
    })
    toRemove.forEach(obj => this.effectsGroup.remove(obj))
  }

  /**
   * 更新棋盘布局
   */
  updateBoard(layout) {
    // 清除现有棋子
    this.pieces.forEach(piece => this.piecesGroup.remove(piece))
    this.pieces.clear()
    
    // 创建新棋子
    layout.forEach(({ position, piece }) => {
      this.createPiece(piece, position)
    })
  }

  /**
   * 处理窗口大小变化
   */
  _handleResize() {
    if (!this.camera || !this.renderer) return
    
    const width = this.canvas.clientWidth
    const height = this.canvas.clientHeight
    
    this.camera.aspect = width / height
    this.camera.updateProjectionMatrix()
    
    this.renderer.setSize(width, height)
  }

  /**
   * 开始渲染循环
   */
  _startRenderLoop() {
    this._isRunning = true
    this._lastTime = performance.now()
    
    const render = (time) => {
      if (!this._isRunning) return
      
      this._animationId = requestAnimationFrame(render)
      
      // 计算时间增量
      const deltaTime = Math.min((time - this._lastTime) / 1000, 0.1)
      this._lastTime = time
      
      // 更新控制器
      if (this.controls) {
        this.controls.update()
      }
      
      // 光源固定在空间坐标，不随相机移动
      // 这样阴影保持稳定，不会因视角变化而漂移
      // 光源位置在 _initLighting() 中设置为 (10, 15, 10)
      
      // 更新粒子系统
      if (this.particles) {
        this.particles.update(deltaTime)
      }
      
      // 渲染场景
      this.renderer.render(this.scene, this.camera)
    }
    
    render(performance.now())
  }

  /**
   * 动画移动相机
   * 
   * @param {Object} targetPos - 目标位置 {x, y, z}
   * @param {Object} lookAt - 观察点 {x, y, z}
   * @param {number} duration - 动画持续时间(秒)
   * @returns {Promise}
   */
  animateCamera(targetPos, lookAt, duration = 1.0) {
    return new Promise((resolve) => {
      const startPos = this.camera.position.clone()
      const startLookAt = this.controls.target.clone()
      const startTime = performance.now()
      
      // 禁用控制器
      this.controls.enabled = false
      
      const easeOutCubic = t => 1 - Math.pow(1 - t, 3)
      
      const animate = (time) => {
        const elapsed = (time - startTime) / 1000
        const progress = Math.min(elapsed / duration, 1)
        const eased = easeOutCubic(progress)
        
        // 插值位置
        this.camera.position.x = startPos.x + (targetPos.x - startPos.x) * eased
        this.camera.position.y = startPos.y + (targetPos.y - startPos.y) * eased
        this.camera.position.z = startPos.z + (targetPos.z - startPos.z) * eased
        
        // 插值观察点
        this.controls.target.x = startLookAt.x + (lookAt.x - startLookAt.x) * eased
        this.controls.target.y = startLookAt.y + (lookAt.y - startLookAt.y) * eased
        this.controls.target.z = startLookAt.z + (lookAt.z - startLookAt.z) * eased
        
        if (progress < 1) {
          requestAnimationFrame(animate)
        } else {
          // 重新启用控制器
          this.controls.enabled = true
          resolve()
        }
      }
      
      requestAnimationFrame(animate)
    })
  }

  /**
   * 重置相机到默认位置
   */
  resetCamera(duration = 1.0) {
    const [x, y, z] = this.options.cameraPosition
    return this.animateCamera({ x, y, z }, { x: 0, y: 0, z: 0 }, duration)
  }

  /**
   * 停止渲染
   */
  stop() {
    this._isRunning = false
    if (this._animationId) {
      cancelAnimationFrame(this._animationId)
    }
  }

  /**
   * 显示将军效果
   * 
   * @param {string} kingIccs - 被将军的将/帅位置
   */
  showCheck(kingIccs) {
    // 播放将军音效
    if (this.sounds) {
      this.sounds.playCheck()
    }
    
    // 创建粒子效果
    if (this.particles && kingIccs) {
      const pos = this._iccsToWorld(kingIccs)
      this.particles.createCheckWarning(pos)
    }
    
    // 高亮被将军的棋子
    const king = this.pieces.get(kingIccs)
    if (king) {
      // 保存原始材质
      if (!king.userData.originalMaterials) {
        king.userData.originalMaterials = []
        king.traverse((child) => {
          if (child.material) {
            king.userData.originalMaterials.push(child.material.clone())
          }
        })
      }
      
      // 闪烁效果
      let flashCount = 0
      const maxFlashes = 6
      const flashInterval = setInterval(() => {
        king.traverse((child) => {
          if (child.material && child.material.emissive) {
            if (flashCount % 2 === 0) {
              child.material.emissive.setHex(0xff0000)
              child.material.emissiveIntensity = 0.5
            } else {
              child.material.emissive.setHex(0x000000)
              child.material.emissiveIntensity = 0
            }
          }
        })
        
        flashCount++
        if (flashCount >= maxFlashes) {
          clearInterval(flashInterval)
          // 恢复原始材质
          king.traverse((child) => {
            if (child.material) {
              child.material.emissive.setHex(0x000000)
              child.material.emissiveIntensity = 0
            }
          })
        }
      }, 200)
    }
  }

  /**
   * 销毁场景
   */
  dispose() {
    this.stop()
    
    // 停止所有动画
    if (this.animator) {
      this.animator.stopAll()
    }
    
    // 清理粒子
    if (this.particles) {
      this.particles.clear()
    }
    
    window.removeEventListener('resize', () => this._handleResize())
    
    if (this.renderer) {
      this.renderer.dispose()
    }
    
    if (this.controls) {
      this.controls.dispose()
    }
  }
}

export { RENDERER_TYPE, BOARD_CONFIG, PIECE_CONFIG }
