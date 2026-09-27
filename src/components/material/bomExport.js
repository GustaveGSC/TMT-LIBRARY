// ── 研发 BOM 导出 Excel（物料BOM 页与物料卡片 BOM 弹窗共用）──
// 后端按页面上的树生成 xlsx（序号按层级编号、编码按层级缩进），这里只负责下载。
import { ElMessage } from 'element-plus'
import http from '@/api/http'
import { downloadBlob } from '@/utils/download'

// xlsx 是 zip 包，以 PK\x03\x04 开头；不是的话多半是后端返回的 JSON 错误
function isXlsx(buf) {
  const b = new Uint8Array(buf || [])
  return b[0] === 0x50 && b[1] === 0x4B && b[2] === 0x03 && b[3] === 0x04
}

function errorMessage(buf) {
  try {
    return JSON.parse(new TextDecoder().decode(buf)).message || '导出失败'
  } catch {
    return '导出失败'
  }
}

/**
 * 导出一份 BOM 的完整多层结构
 * @param {{ id: number, drawing: string }} bom
 * @returns {Promise<boolean>} 是否成功开始下载
 */
export async function exportBom(bom) {
  if (!bom?.id) return false
  try {
    const buf = await http.get(`/api/material/boms/${bom.id}/export`, { responseType: 'arraybuffer' })
    if (!isXlsx(buf)) {
      ElMessage.error(errorMessage(buf))
      return false
    }
    downloadBlob(buf, `BOM-${bom.drawing}.xlsx`)
    return true
  } catch (e) {
    ElMessage.error(e.message || '导出失败')
    return false
  }
}
