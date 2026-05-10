/**
 * 触发浏览器下载 ArrayBuffer 为 Excel 文件（网页端导出使用）
 * @param {ArrayBuffer} buffer
 * @param {string} filename
 */
export function downloadBlob(buffer, filename) {
  const blob = new Blob([buffer], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

/**
 * 网页端弹出文件选择框，返回选中的 File 对象
 * @param {string} accept - MIME 类型或扩展名，如 '.xlsx' 或 'image/png'
 * @returns {Promise<File|null>}
 */
export function pickFile(accept) {
  return new Promise((resolve) => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = accept
    input.onchange = () => resolve(input.files?.[0] ?? null)
    input.oncancel = () => resolve(null)
    input.click()
  })
}
