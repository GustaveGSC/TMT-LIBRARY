import { app } from 'electron'
import { spawn, spawnSync, ChildProcess } from 'child_process'
import { join } from 'path'
import { existsSync, chmodSync, cpSync, mkdirSync } from 'fs'

let pythonProcess: ChildProcess | null = null
const PYTHON_PORT = 8765           // Flask 监听端口，与前端 api/http.js 保持一致
const MAX_WAIT_MS = 10000          // 最多等待 10 秒

// ── 获取 Python 可执行文件路径 ────────────────────
function getPythonExecutable(): string {
  if (app.isPackaged) {
    const isWin   = process.platform === 'win32'
    const exeName = isWin ? 'backend.exe' : 'backend'
    // PyInstaller --onefile --name backend 产出：python-backend/{backend|backend.exe}
    const srcExe  = join(process.resourcesPath, 'python-backend', exeName)

    if (!isWin) {
      // macOS/Linux：优先直接 chmod；若文件系统只读（如从 DMG 直接运行），
      // 则将整个 python-backend 目录复制到可写的 userData 再启动
      try {
        chmodSync(srcExe, 0o755)
        return srcExe
      } catch {
        // 只读文件系统（DMG），复制到 userData
        const destBase = join(app.getPath('userData'), 'python-backend')
        const destExe  = join(destBase, exeName)
        if (!existsSync(destExe)) {
          mkdirSync(destBase, { recursive: true })
          cpSync(join(process.resourcesPath, 'python-backend'), destBase, { recursive: true })
        }
        try { chmodSync(destExe, 0o755) } catch { /* ignore */ }
        return destExe
      }
    }

    return srcExe
  } else {
    // 开发：直接用系统 Python
    return process.platform === 'win32' ? 'python' : 'python3'
  }
}

// ── 等待 Flask 就绪（轮询健康检查接口）───────────
async function waitForPython(timeoutMs = MAX_WAIT_MS): Promise<void> {
  const start = Date.now()
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(`http://127.0.0.1:${PYTHON_PORT}/health`)
      if (res.ok) return
    } catch {
      // 还没启动，继续等
    }
    await new Promise(r => setTimeout(r, 300))
  }
  throw new Error(`Python backend failed to start within ${timeoutMs}ms`)
}

// ── 清理同名僵尸进程 ─────────────────────────────
function killZombieBackends(): void {
  if (!app.isPackaged) return
  try {
    if (process.platform === 'win32') {
      // 强制杀掉所有 backend.exe（含僵尸），避免端口占用和连接泄漏
      spawnSync('taskkill', ['/f', '/im', 'backend.exe', '/t'], { stdio: 'ignore' })
    } else {
      spawnSync('pkill', ['-f', 'backend'], { stdio: 'ignore' })
    }
  } catch { /* 无残留进程时忽略 */ }
}

// ── 启动 Python ───────────────────────────────────
export async function startPython(): Promise<void> {
  const executable = getPythonExecutable()

  if (!app.isPackaged && !existsSync('backend/app.py')) {
    console.warn('[python] backend/app.py not found, skipping')
    return
  }

  // 启动前清理上次未正常退出留下的僵尸进程
  killZombieBackends()

  const args = app.isPackaged
    ? []                                       // 生产：直接运行可执行文件
    : ['backend/app.py', '--port', String(PYTHON_PORT)]  // 开发：传参给 Flask

  pythonProcess = spawn(executable, args, {
    env: {
      ...process.env,
      FLASK_PORT: String(PYTHON_PORT),
      FLASK_ENV: app.isPackaged ? 'production' : 'development'
    },
    // 生产环境隐藏控制台窗口（Windows）
    windowsHide: true
  })

  pythonProcess.stdout?.on('data', d => console.log('[python]', d.toString().trim()))
  pythonProcess.stderr?.on('data', d => console.error('[python:err]', d.toString().trim()))
  pythonProcess.on('exit', code => console.log(`[python] exited with code ${code}`))

  // 等待后端就绪
  await waitForPython()
  console.log(`[python] backend ready on port ${PYTHON_PORT}`)
}

// ── 停止 Python ───────────────────────────────────
export function stopPython(): void {
  if (!pythonProcess || pythonProcess.killed) return

  const pid = pythonProcess.pid
  if (pid) {
    if (process.platform === 'win32') {
      // Windows：同步强制杀掉整个进程树，确保退出前 backend 已停止
      spawnSync('taskkill', ['/pid', String(pid), '/f', '/t'])
    } else {
      // macOS / Linux：杀掉进程组
      try { process.kill(-pid, 'SIGKILL') } catch { /* already gone */ }
    }
  }

  pythonProcess = null
}