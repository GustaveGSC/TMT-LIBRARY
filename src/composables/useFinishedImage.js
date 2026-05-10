// ── 成品展开行图片 / 裁剪逻辑 ──────────────────────────────────────
import { ref, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import Cropper from 'cropperjs'
import 'cropperjs/dist/cropper.css'
import { pickFile } from '@/utils/download.js'

export function useFinishedImage(props) {
  // ── 状态 ──────────────────────────────────────────
  const imgHover        = ref(false)   // 编辑状态下鼠标悬停
  const imgPreview      = ref(false)   // 预览弹窗开关
  const addMenuVisible  = ref(false)   // 新增子菜单

  const localCoverImage = ref('')      // 裁剪后本地预览（base64），保存前显示用
  const savedCoverImage = ref('')      // 进入编辑时的快照，取消时回退

  const cropDialogVisible = ref(false)
  const cropImgSrc  = ref('')
  const cropImgRef  = ref(null)
  const cropperInst = ref(null)
  const cropSquare  = ref(false)   // 是否锁定正方形

  // ── 方法 ──────────────────────────────────────────

  // 初始化 Cropper（dialog opened 后调用）
  function initCropper() {
    if (cropperInst.value) { cropperInst.value.destroy(); cropperInst.value = null }
    const img = cropImgRef.value
    if (!img) return
    const setup = () => {
      cropperInst.value = new Cropper(img, {
        aspectRatio: cropSquare.value ? 1 : NaN,
        viewMode: 1,
        autoCropArea: 0.8,
      })
    }
    if (img.complete && img.naturalWidth) setup()
    else img.addEventListener('load', setup, { once: true })
  }

  // 正方形开关切换时同步 aspectRatio
  watch(cropSquare, (val) => {
    cropperInst.value?.setAspectRatio(val ? 1 : NaN)
  })

  // 确认裁剪：contain 缩放后居中绘制到 600×600 白底画布
  function applyCrop() {
    if (!cropperInst.value) return
    const src = cropperInst.value.getCroppedCanvas({
      imageSmoothingEnabled: true, imageSmoothingQuality: 'high',
    })
    const out = document.createElement('canvas')
    out.width = 600; out.height = 600
    const ctx = out.getContext('2d')
    ctx.fillStyle = '#ffffff'
    ctx.fillRect(0, 0, 600, 600)
    const scale = Math.min(600 / src.width, 600 / src.height)
    const w = Math.round(src.width  * scale)
    const h = Math.round(src.height * scale)
    const x = Math.round((600 - w) / 2)
    const y = Math.round((600 - h) / 2)
    ctx.drawImage(src, x, y, w, h)
    localCoverImage.value = out.toDataURL('image/png')
    closeCropDialog()
  }

  function closeCropDialog() {
    cropDialogVisible.value = false
    if (cropperInst.value) { cropperInst.value.destroy(); cropperInst.value = null }
  }

  function previewImage() {
    if (!localCoverImage.value && !props.row.cover_image) return
    imgPreview.value = true
  }

  function editImage() {
    cropImgSrc.value = localCoverImage.value || props.row.cover_image
    cropDialogVisible.value = true
  }

  async function addImageFromUpload() {
    addMenuVisible.value = false
    if (window.electronAPI) {
      // Electron：原生文件对话框
      const result = await window.electronAPI.showOpenDialog({
        filters: [{ name: 'PNG 图片', extensions: ['png'] }],
        properties: ['openFile'],
      })
      if (result.canceled || !result.filePaths.length) return
      cropImgSrc.value = await window.electronAPI.readFileAsDataURL(result.filePaths[0])
    } else {
      // 网页端：HTML5 文件选择
      const file = await pickFile('image/png')
      if (!file) return
      cropImgSrc.value = await new Promise((resolve) => {
        const reader = new FileReader()
        reader.onload = e => resolve(e.target.result)
        reader.readAsDataURL(file)
      })
    }
    cropDialogVisible.value = true
  }

  function addImageFromExisting() {
    addMenuVisible.value = false
    // TODO: 从已有图片库选择
  }

  async function deleteImage() {
    try {
      await ElMessageBox.confirm('确认删除当前封面图片？', '删除确认', {
        confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
      })
      localCoverImage.value = ''
    } catch {}
  }

  return {
    imgHover, imgPreview, addMenuVisible,
    localCoverImage, savedCoverImage,
    cropDialogVisible, cropImgSrc, cropImgRef, cropperInst, cropSquare,
    initCropper, applyCrop, closeCropDialog,
    previewImage, editImage, addImageFromUpload, addImageFromExisting, deleteImage,
  }
}
