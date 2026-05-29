/**
 * 本地语义模型管理（bge-small-zh-v1.5 ONNX 量化版）
 * - 模型文件存储在 ~/.tmt-library/models/bge-small-zh-v1.5/
 * - 从 OSS 下载到本地，不经过服务器
 * - 使用 @xenova/transformers 在主进程推理（onnxruntime-node）
 */
import * as fs from 'fs'
import * as https from 'https'
import * as http from 'http'
import * as path from 'path'
import * as os from 'os'
import { WebContents } from 'electron'

// ── 常量 ──────────────────────────────────────────────────────────────────────
const OSS_BASE = 'https://tmt-oss.oss-cn-hangzhou.aliyuncs.com/tmt-library/models/bge-small-zh-v1.5'
const MODEL_DIR_NAME = 'bge-small-zh-v1.5'

const MODEL_FILES: Array<{ name: string; approxSize: number }> = [
  { name: 'config.json',               approxSize: 762 },
  { name: 'tokenizer_config.json',     approxSize: 434 },
  { name: 'tokenizer.json',            approxSize: 433_781 },
  { name: 'onnx/model_quantized.onnx', approxSize: 23_000_000 },
]

const TOTAL_BYTES_APPROX = MODEL_FILES.reduce((s, f) => s + f.approxSize, 0)

// ── 路径 ──────────────────────────────────────────────────────────────────────
function getModelDir(): string {
  return path.join(os.homedir(), '.tmt-library', 'models', MODEL_DIR_NAME)
}

export function isModelInstalled(): boolean {
  const dir = getModelDir()
  return (
    fs.existsSync(path.join(dir, 'tokenizer.json')) &&
    fs.existsSync(path.join(dir, 'onnx', 'model_quantized.onnx'))
  )
}

// ── 下载状态 ──────────────────────────────────────────────────────────────────
interface DownloadState {
  running: boolean
  done: boolean
  error: string | null
  downloadedBytes: number
  totalBytes: number
  currentFile: string
  fileIndex: number
  fileTotal: number
  percent: number
}

let _state: Omit<DownloadState, 'percent'> = {
  running: false, done: false, error: null,
  downloadedBytes: 0, totalBytes: TOTAL_BYTES_APPROX,
  currentFile: '', fileIndex: 0, fileTotal: MODEL_FILES.length,
}

export function getDownloadState(): DownloadState {
  const percent = _state.totalBytes
    ? Math.min(100, Math.round(_state.downloadedBytes / _state.totalBytes * 100))
    : 0
  return { ..._state, percent }
}

// ── 下载单个文件 ──────────────────────────────────────────────────────────────
function downloadFile(
  url: string,
  dest: string,
  onChunk: (bytes: number) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    fs.mkdirSync(path.dirname(dest), { recursive: true })
    const tmp = dest + '.tmp'
    const fileStream = fs.createWriteStream(tmp)
    const client = url.startsWith('https') ? https : http

    const req = client.get(url, { timeout: 30_000 }, (res) => {
      if (res.statusCode !== 200) {
        fileStream.close()
        try { fs.unlinkSync(tmp) } catch { /* ignore */ }
        return reject(new Error(`HTTP ${res.statusCode}: ${url}`))
      }
      res.on('data', (chunk: Buffer) => onChunk(chunk.length))
      res.pipe(fileStream)
      fileStream.on('finish', () => {
        fileStream.close()
        try { fs.renameSync(tmp, dest) } catch (e) { return reject(e) }
        resolve()
      })
    })

    req.on('error', (e) => {
      fileStream.close()
      try { fs.unlinkSync(tmp) } catch { /* ignore */ }
      reject(e)
    })

    req.on('timeout', () => {
      req.destroy()
      fileStream.close()
      try { fs.unlinkSync(tmp) } catch { /* ignore */ }
      reject(new Error(`Timeout: ${url}`))
    })
  })
}

// ── 启动下载 ──────────────────────────────────────────────────────────────────
export async function startDownload(sender?: WebContents): Promise<void> {
  if (_state.running) return

  _state = {
    running: true, done: false, error: null,
    downloadedBytes: 0, totalBytes: TOTAL_BYTES_APPROX,
    currentFile: '', fileIndex: 0, fileTotal: MODEL_FILES.length,
  }

  const dir = getModelDir()

  try {
    for (let i = 0; i < MODEL_FILES.length; i++) {
      const { name } = MODEL_FILES[i]
      _state.currentFile = name
      _state.fileIndex   = i + 1
      sender?.send('model:progress', getDownloadState())

      const dest = path.join(dir, name)

      // 已存在则跳过（按文件粒度断点续传）
      if (fs.existsSync(dest)) {
        _state.downloadedBytes += fs.statSync(dest).size
        sender?.send('model:progress', getDownloadState())
        continue
      }

      const url = `${OSS_BASE}/${name}`
      await downloadFile(url, dest, (bytes) => {
        _state.downloadedBytes += bytes
        sender?.send('model:progress', getDownloadState())
      })
    }

    _state.done    = true
    _state.running = false
    sender?.send('model:progress', getDownloadState())

    // 下载完成后立即加载模型
    loadModel().catch(() => { /* 加载失败不影响流程 */ })

  } catch (e: any) {
    _state.error   = e?.message || String(e)
    _state.running = false
    sender?.send('model:progress', getDownloadState())
  }
}

// ── 模型加载 ──────────────────────────────────────────────────────────────────
let _pipeline: any  = null
let _loadPromise: Promise<void> | null = null

export function isModelReady(): boolean {
  return _pipeline !== null
}

export async function loadModel(): Promise<void> {
  if (_pipeline) return
  if (_loadPromise) return _loadPromise
  if (!isModelInstalled()) return

  _loadPromise = (async () => {
    try {
      // 动态导入，避免主进程启动时 onnxruntime-node 影响启动速度
      const { pipeline, env } = await import('@xenova/transformers' as any)
      // 指向本地目录，禁止联网下载
      env.localModelPath   = getModelDir().replace(/[\\/]$/, '') + path.sep + '..' + path.sep
      env.allowRemoteModels = false
      _pipeline = await pipeline('feature-extraction', MODEL_DIR_NAME, { quantized: true })
      console.log('[model] loaded successfully')
    } catch (e) {
      console.error('[model] load failed:', e)
      _pipeline = null
    } finally {
      _loadPromise = null
    }
  })()

  return _loadPromise
}

// ── 文本编码 ──────────────────────────────────────────────────────────────────
export async function encodeTexts(texts: string[]): Promise<number[][]> {
  if (!_pipeline) {
    await loadModel()
    if (!_pipeline) throw new Error('Model not available')
  }

  const output = await _pipeline(texts, { pooling: 'mean', normalize: true })
  // output.data: Float32Array, shape [texts.length, dim]
  const dim    = output.dims[output.dims.length - 1] as number
  const result: number[][] = []
  for (let i = 0; i < texts.length; i++) {
    result.push(Array.from(output.data.slice(i * dim, (i + 1) * dim) as Float32Array))
  }
  return result
}
