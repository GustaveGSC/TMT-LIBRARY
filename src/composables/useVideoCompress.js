import { ref } from 'vue'
import { FFmpeg } from '@ffmpeg/ffmpeg'
import { fetchFile, toBlobURL } from '@ffmpeg/util'

// FFmpeg 单例，避免重复加载（wasm 文件较大）
let ffmpegInstance = null
let loadPromise   = null

async function getFFmpeg(onProgress) {
  if (!ffmpegInstance) {
    ffmpegInstance = new FFmpeg()
  }
  if (!loadPromise) {
    loadPromise = (async () => {
      console.log('[FFmpeg] 开始加载 wasm…')
      // 用绝对 URL 引用本地 public 目录下的文件，toblobURL fetch 后转成 blob URL
      // 这样 worker 内部不依赖相对路径解析，避免 blob: URL 无相对路径的问题
      const base    = window.location.origin
      const coreURL = await toBlobURL(`${base}/ffmpeg/ffmpeg-core.js`,   'text/javascript')
      const wasmURL = await toBlobURL(`${base}/ffmpeg/ffmpeg-core.wasm`, 'application/wasm')
      console.log('[FFmpeg] core/wasm 已转为 blob URL，调用 load…')
      await ffmpegInstance.load({ coreURL, wasmURL })
      console.log('[FFmpeg] 加载完成')
    })().catch(e => {
      console.error('[FFmpeg] 加载失败:', e)
      ffmpegInstance = null
      loadPromise    = null
      throw e
    })
  }
  await loadPromise
  if (onProgress) {
    ffmpegInstance.on('progress', onProgress)
  }
  return ffmpegInstance
}

export function useVideoCompress() {
  const compressing     = ref(false)
  const compressPercent = ref(0)

  async function compressVideo(file) {
    compressing.value     = true
    compressPercent.value = 0

    const onProgress = ({ progress }) => {
      compressPercent.value = Math.min(99, Math.round(progress * 100))
    }

    try {
      const ff = await getFFmpeg(onProgress)

      const inputName  = 'input.mp4'
      const outputName = 'output.mp4'

      console.log('[FFmpeg] 写入文件:', file.name, file.size, 'bytes')
      await ff.writeFile(inputName, await fetchFile(file))
      console.log('[FFmpeg] 开始压缩…')
      await ff.exec([
        '-i', inputName,
        '-vcodec', 'libx264',
        '-crf', '28',
        '-preset', 'ultrafast',   // 单线程用 ultrafast，速度优先
        '-acodec', 'aac',
        '-movflags', '+faststart', // 边下边播优化
        outputName,
      ])

      const data = await ff.readFile(outputName)
      // 清理内存
      await ff.deleteFile(inputName)
      await ff.deleteFile(outputName)
      ff.off('progress', onProgress)

      compressPercent.value = 100
      console.log('[FFmpeg] 压缩完成，输出大小:', data.byteLength, 'bytes')
      const compressed = new File([data.buffer], file.name, { type: 'video/mp4' })
      return compressed
    } catch (e) {
      console.error('[FFmpeg] 压缩失败:', e)
      throw e instanceof Error ? e : new Error(String(e))
    } finally {
      compressing.value     = false
      compressPercent.value = 0
    }
  }

  return { compressing, compressPercent, compressVideo }
}
