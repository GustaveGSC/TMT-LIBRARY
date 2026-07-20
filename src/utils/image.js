/**
 * 判断产品封面图是否为高清图（原始图短边 ≥ 1200px）
 * @param {{ cover_image_original?: string, cover_image_width?: number, cover_image_height?: number }} item
 */
export function isHighRes(item) {
  return !!(
    item?.cover_image_original &&
    Math.min(item.cover_image_width || 0, item.cover_image_height || 0) >= 1200
  )
}
