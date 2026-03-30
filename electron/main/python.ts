import { app } from 'electron'
import { spawn, ChildProcess } from 'child_process'
import { join } from 'path'
import { existsSync, chmodSync } from 'fs'

let pythonProcess: ChildProcess | null = null
const PYTHON_PORT = 8765           // Flask 监听端口，与前端 api/http.js 保持一致
const MAX_WAIT_MS = 10000          // 最多等待 10 秒

// ── 获取 Python 可执行文件路径 ────────────────────
function getPythonExecutable(): string {
  if (app.isPackaged) {
    // 生产：使用打包进 resources 的 PyInstaller 产物
    const platform = process.platform
    const exeName = platform === 'win32' ? 'backend.exe' : 'backend'
    return join(process.resourcesPath, 'python-backend', exeName)
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

// ── 启动 Python ───────────────────────────────────
export async function startPython(): Promise<void> {
  const executable = getPythonExecutable()

  if (!app.isPackaged && !existsSync('backend/app.py')) {
    console.warn('[python] backend/app.py not found, skipping')
    return
  }

  const args = app.isPackaged
    ? []                                       // 生产：直接运行可执行文件
    : ['backend/app.py', '--port', String(PYTHON_PORT)]  // 开发：传参给 Flask

  // macOS/Linux 打包后可执行权限可能丢失，补加
  if (app.isPackaged && process.platform !== 'win32') {
    try { chmodSync(executable, 0o755) } catch { /* 已有权限则忽略 */ }
  }

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
      // Windows：强制杀掉整个进程树
      spawn('taskkill', ['/pid', String(pid), '/f', '/t'])
    } else {
      // macOS / Linux：杀掉进程组
      process.kill(-pid, 'SIGTERM')
    }
  }

  pythonProcess = null
}