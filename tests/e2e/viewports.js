// 响应式回归测试的公共视口矩阵
// 见 handoff/2026-07-23-codex-responsive-ui-redesign-proposal.md 第八节
export const VIEWPORTS = [
  { name: '1920x1080-standard-desktop',        width: 1920, height: 1080 },
  { name: '1536x864-1080p-at-125pct',          width: 1536, height: 864 },
  { name: '1280x720-low-res-desktop',          width: 1280, height: 720 },
  { name: '1093x614-1366x768-at-125pct',       width: 1093, height: 614 },
  { name: '911x512-1366x768-at-150pct',        width: 911,  height: 512 },
  { name: '768x1024-tablet',                   width: 768,  height: 1024 },
  { name: '390x844-mobile-portrait',           width: 390,  height: 844 },
  { name: '844x390-mobile-landscape',          width: 844,  height: 390 },
]
