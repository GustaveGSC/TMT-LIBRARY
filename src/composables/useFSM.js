import { ref } from 'vue'

// 通用有限状态机：transitions[currentState][event] = nextState
// 事件在当前状态下未定义时，send() 直接忽略（不抛错、不跳变）
export function useFSM(transitions, initial) {
  const state = ref(initial)

  function send(event) {
    const next = transitions[state.value]?.[event]
    if (next === undefined) return false
    state.value = next
    return true
  }

  function can(event) {
    return transitions[state.value]?.[event] !== undefined
  }

  return { state, send, can }
}
