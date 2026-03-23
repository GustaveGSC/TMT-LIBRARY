import Sortable from 'sortablejs'

/**
 * 轻量封装 SortableJS
 * @param {HTMLElement} el - 拖拽列表容器元素
 * @param {Function} onEnd - 拖拽结束回调 ({ oldIndex, newIndex })
 * @param {Object} options - 额外的 SortableJS 配置（可选）
 * @returns {Sortable} SortableJS 实例（调用 .destroy() 销毁）
 */
export function initSortable(el, onEnd, options = {}) {
  return Sortable.create(el, {
    animation: 150,
    handle: '.drag-handle',
    ghostClass: 'sortable-ghost',
    chosenClass: 'sortable-chosen',
    onEnd({ oldIndex, newIndex }) {
      if (oldIndex !== newIndex) onEnd({ oldIndex, newIndex })
    },
    ...options,
  })
}
