(() => {
  'use strict'

  const PDFJS_CDN = 'https://registry.npmmirror.com/pdfjs-dist/3.11.174/files/build/'
  const viewer = document.getElementById('pdf-viewer')
  if (!viewer) return

  const pdfUrl = viewer.dataset.pdfUrl
  const filename = viewer.dataset.filename || 'file.pdf'
  const message = document.getElementById('msg')
  const download = document.getElementById('dl')
  const pages = document.getElementById('pages')

  function showError(detail) {
    message.replaceChildren(document.createTextNode(detail), document.createElement('br'))
    const link = document.createElement('a')
    link.href = pdfUrl
    link.download = filename
    link.textContent = '点此下载 PDF'
    message.appendChild(link)
  }

  const timeout = window.setTimeout(() => {
    download.style.display = 'inline'
  }, 8000)

  const script = document.createElement('script')
  script.src = `${PDFJS_CDN}pdf.min.js`
  script.onerror = () => {
    window.clearTimeout(timeout)
    showError('PDF 加载失败，请下载后查看。')
  }
  script.onload = async () => {
    try {
      window.pdfjsLib.GlobalWorkerOptions.workerSrc = `${PDFJS_CDN}pdf.worker.min.js`
      const pdf = await window.pdfjsLib.getDocument(pdfUrl).promise
      window.clearTimeout(timeout)
      message.style.display = 'none'
      const width = window.innerWidth - 16
      for (let number = 1; number <= pdf.numPages; number += 1) {
        const page = await pdf.getPage(number)
        const baseViewport = page.getViewport({ scale: 1 })
        const viewport = page.getViewport({ scale: width / baseViewport.width })
        const canvas = document.createElement('canvas')
        canvas.width = viewport.width
        canvas.height = viewport.height
        pages.appendChild(canvas)
        await page.render({ canvasContext: canvas.getContext('2d'), viewport }).promise
      }
    } catch (error) {
      window.clearTimeout(timeout)
      showError(`加载失败：${error instanceof Error ? error.message : '未知错误'}`)
    }
  }
  document.head.appendChild(script)
})()
