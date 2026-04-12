/**
 * 游戏状态管理器
 * 
 * 功能:
 * - 管理游戏状态 (FEN、回合、历史等)
 * - FEN 字符串解析
 * - ICCS 坐标转换
 * - 走步历史追踪
 */

// 棋子字符到名称的映射
const PIECE_NAMES = {
  // 红方 (大写)
  'K': '帅', 'A': '仕', 'B': '相', 'N': '馬', 'R': '車', 'C': '炮', 'P': '兵',
  // 黑方 (小写)
  'k': '将', 'a': '士', 'b': '象', 'n': '马', 'r': '车', 'c': '砲', 'p': '卒',
}

// ICCS 列字母到索引的映射
const ICCS_COLS = 'abcdefghi'

// 游戏状态
const GAME_STATUS = {
  WAITING: 'waiting',
  PLAYING: 'playing',
  FINISHED: 'finished',
}

export class GameStateManager {
  constructor() {
    this.reset()
  }

  /**
   * 重置状态
   */
  reset() {
    this.fen = ''
    this.turn = 'Red' // 'Red' 或 'Black'
    this.turnNumber = 1
    this.moveHistory = []
    this.legalMoves = []
    this.players = {
      Red: { name: '红方', model: '' },
      Black: { name: '黑方', model: '' },
    }
    this.lastMove = null
    this.status = GAME_STATUS.WAITING
    this.result = null
    this.resultReason = ''
    
    // 棋盘状态 (9x10 矩阵，从黑方视角)
    this.board = Array(10).fill(null).map(() => Array(9).fill(null))
    
    // 监听器
    this._listeners = new Set()
  }

  /**
   * 添加状态变化监听器
   */
  addListener(callback) {
    this._listeners.add(callback)
    return () => this._listeners.delete(callback)
  }

  /**
   * 通知所有监听器
   */
  _notify(changeType, data) {
    this._listeners.forEach(cb => {
      try {
        cb(changeType, data, this)
      } catch (error) {
        console.error('[GameState] Listener error:', error)
      }
    })
  }

  /**
   * 从服务器初始化状态
   */
  initFromServer(state) {
    this.fen = state.fen || ''
    this.turn = state.turn || 'Red'
    this.turnNumber = state.turn_number || 1
    this.moveHistory = state.move_history || []
    this.legalMoves = state.legal_moves || []
    this.status = state.status || GAME_STATUS.PLAYING
    this.result = state.result || null
    this.resultReason = state.result_reason || ''
    
    if (state.players) {
      this.players = {
        Red: state.players.Red || { name: '红方', model: '' },
        Black: state.players.Black || { name: '黑方', model: '' },
      }
    }
    
    if (state.last_move) {
      this.lastMove = state.last_move
    }
    
    this._parseFen()
    this._notify('init', state)
  }

  /**
   * 处理移动事件
   */
  handleMove(moveEvent) {
    const { move, from_pos, to_pos, fen_after, turn, turn_number } = moveEvent
    
    // 保存旧状态用于动画
    const fromPiece = this.getPieceAtIccs(from_pos)
    const toPiece = this.getPieceAtIccs(to_pos)
    
    // 更新状态
    this.fen = fen_after
    this.turn = turn
    this.turnNumber = turn_number
    
    if (move) {
      this.moveHistory.push(move)
    }
    
    this.lastMove = {
      move,
      from_pos,
      to_pos,
      piece: fromPiece,
      captured: toPiece,
    }
    
    // 解析新 FEN
    this._parseFen()
    
    this._notify('move', {
      move,
      from: from_pos,
      to: to_pos,
      piece: fromPiece,
      captured: toPiece,
    })
  }

  /**
   * 处理游戏结束
   */
  handleGameOver(gameOverEvent) {
    this.status = GAME_STATUS.FINISHED
    this.result = gameOverEvent.result
    this.resultReason = gameOverEvent.result_reason
    
    this._notify('gameOver', gameOverEvent)
  }

  /**
   * 解析 FEN 字符串
   * 
   * FEN 格式: 棋子布局 当前方 吃子计数 回合数
   * 示例: rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1
   */
  _parseFen() {
    if (!this.fen) return
    
    const parts = this.fen.split(' ')
    const boardPart = parts[0]
    
    // 解析棋盘
    this.board = Array(10).fill(null).map(() => Array(9).fill(null))
    
    const rows = boardPart.split('/')
    for (let row = 0; row < rows.length && row < 10; row++) {
      const rowStr = rows[row]
      let col = 0
      
      for (const char of rowStr) {
        if (col >= 9) break
        
        if (char >= '1' && char <= '9') {
          // 数字表示空位数量
          col += parseInt(char)
        } else if (PIECE_NAMES[char]) {
          // 棋子
          // 关键修复: FEN row 0 是黑方底线，需要存储到 board[9]
          // 与引擎的 9-row 翻转保持一致，确保红黑方棋子位置正确对应
          this.board[9 - row][col] = char
          col++
        }
      }
    }
    
    // 解析当前方
    if (parts[1]) {
      this.turn = parts[1] === 'w' ? 'Red' : 'Black'
    }
    
    // 解析回合数
    if (parts[5]) {
      this.turnNumber = parseInt(parts[5])
    }
  }

  /**
   * ICCS 坐标转棋盘索引
   * ICCS: 列(a-i) + 行(0-9)
   * 索引: [row, col] - row 从 0-9(黑方到红方)，col 从 0-8(左到右)
   */
  static iccsToIndex(iccs) {
    if (!iccs || iccs.length < 2) return null
    
    const col = iccs[0].toLowerCase()
    const row = parseInt(iccs.slice(1))
    
    const colIndex = col.charCodeAt(0) - 'a'.charCodeAt(0)
    const rowIndex = row
    
    if (colIndex < 0 || colIndex > 8 || rowIndex < 0 || rowIndex > 9) {
      return null
    }
    
    return [rowIndex, colIndex]
  }

  /**
   * 棋盘索引转 ICCS 坐标
   */
  static indexToIccs(row, col) {
    if (row < 0 || row > 9 || col < 0 || col > 8) return null
    
    const colChar = String.fromCharCode('a'.charCodeAt(0) + col)
    return `${colChar}${row}`
  }

  /**
   * ICCS 转 3D 世界坐标
   */
  static iccsToWorld(iccs, cellSize = 1.0) {
    const index = GameStateManager.iccsToIndex(iccs)
    if (!index) return null
    
    const [row, col] = index
    
    // 棋盘原点在中心，X 向右，Z 向前
    // 行 0（红方底线）-> Z = +4.5（靠近用户）
    // 行 9（黑方底线）-> Z = -4.5（远离用户）
    // 列 0-8 对应 X 从 -4 到 4
    return {
      x: (col - 4) * cellSize,
      y: 0.2, // 棋子高度的一半
      z: (4.5 - row) * cellSize,
    }
  }

  /**
   * 获取指定 ICCS 位置的棋子
   */
  getPieceAtIccs(iccs) {
    const index = GameStateManager.iccsToIndex(iccs)
    if (!index) return null
    
    const [row, col] = index
    return this.board[row]?.[col] || null
  }

  /**
   * 获取棋子名称
   */
  static getPieceName(pieceChar) {
    return PIECE_NAMES[pieceChar] || pieceChar
  }

  /**
   * 获取棋子颜色
   */
  static getPieceColor(pieceChar) {
    if (!pieceChar) return null
    return pieceChar === pieceChar.toUpperCase() ? 'Red' : 'Black'
  }

  /**
   * 获取完整棋盘布局
   * 返回: [{ position: 'a0', piece: 'r', color: 'Black' }, ...]
   */
  getBoardLayout() {
    const layout = []
    
    for (let row = 0; row < 10; row++) {
      for (let col = 0; col < 9; col++) {
        const piece = this.board[row][col]
        if (piece) {
          layout.push({
            position: GameStateManager.indexToIccs(row, col),
            piece,
            color: GameStateManager.getPieceColor(piece),
            name: GameStateManager.getPieceName(piece),
          })
        }
      }
    }
    
    return layout
  }

  /**
   * 格式化回合信息显示
   */
  getTurnDisplay() {
    if (this.status === GAME_STATUS.FINISHED) {
      return '游戏结束'
    }
    
    const turnText = this.turn === 'Red' ? '红方' : '黑方'
    return `第 ${this.turnNumber} 回合 - ${turnText}走棋`
  }

  /**
   * 格式化走步历史
   */
  formatMoveHistory() {
    return this.moveHistory.map((move, index) => {
      const turnNum = Math.floor(index / 2) + 1
      const isRed = index % 2 === 0
      const prefix = isRed ? `${turnNum}.` : ''
      return `${prefix}${move}`
    }).join(' ')
  }
}

export { GAME_STATUS, PIECE_NAMES, ICCS_COLS }
