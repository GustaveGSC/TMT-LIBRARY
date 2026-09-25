/**
 * useMaterialGateCheck — 物料门禁校验 composable
 *
 * 门禁按物料编码登记（提醒 warn / 禁止 block 两级），"PDM转BOM"和"变更申请单填写"
 * 检测到上传文件里出现门禁物料时需要自动提示/阻断。校验逻辑统一走后端
 * POST /api/rd/material-gates/check，这里只是包一层，避免每个调用点重复错误处理。
 */
import http from '@/api/http'

export function useMaterialGateCheck() {
  async function checkMaterialCodes(codes) {
    if (!codes?.length) return { warn: [], block: [], ok: true }
    try {
      const res = await http.post('/api/rd/material-gates/check', { codes })
      if (res.success) {
        return { warn: res.data.warn || [], block: res.data.block || [], ok: true }
      }
      // 接口本身返回失败（非网络异常）：不拿假数据糊弄，明确标记 ok:false 让调用方提示用户
      return { warn: [], block: [], ok: false }
    } catch {
      // 网络/接口异常不阻断主流程（避免因门禁接口不可用导致 PDM转BOM/变更申请单完全无法使用），
      // 但 ok:false 让调用方能提示"门禁校验未完成"，不要悄悄当成"无命中"处理
      return { warn: [], block: [], ok: false }
    }
  }

  return { checkMaterialCodes }
}
