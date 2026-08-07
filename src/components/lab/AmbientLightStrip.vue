<script setup>
// 氛围灯：模拟可寻址灯带（WS2812 类），支持跑马灯效果
// 默认不亮（灯珠暗灭、无光效），由按键层的"氛围灯"开关控制
import { useLabHandsetStore } from '@/stores/lab/handset'

const props = defineProps({
  // 灯带颗数
  count: { type: Number, default: 48 },
  uiScale: { type: Number, default: 1 },
})

const store = useLabHandsetStore()
</script>

<template>
  <div class="ambient-strip" :style="{ '--ui-scale': props.uiScale, '--ambient-color': store.activeAmbientPreset?.color || '#67c8ff', '--ambient-brightness': (store.activeAmbientPreset?.brightness || 65) / 100 }" :class="{ active: store.ambientOn, breathing: store.activeAmbientPreset?.effect === '呼吸', shifting: store.activeAmbientPreset?.effect === '渐变' }" aria-hidden="true">
    <!-- 灯带实体可见，光线向其后方表面扩散。 -->
    <div class="diffuse-field diffuse-field-wide" />
    <div class="diffuse-field diffuse-field-core" />
    <div class="light-fixture">
      <div class="rear-emitter">
        <span
          v-for="i in count"
          :key="i"
          class="emitter-pixel"
          :style="{ '--pixel-index': i }"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.ambient-strip {
  --ui-scale: 1;
  position: relative;
  width: min(660px, 100%);
  height: 94px;
  pointer-events: none;
}

.diffuse-field {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  border-radius: 50%;
  opacity: 0;
  transition: opacity 0.55s ease;
}

.diffuse-field-wide {
  top: 7px;
  width: min(620px, 94vw);
  height: 74px;
  filter: blur(23px);
  background: var(--ambient-color);
  background-size: 180% 100%;
  animation: reflected-marquee 4.2s linear infinite;
}

.diffuse-field-core {
  top: 33px;
  width: min(520px, 82vw);
  height: 38px;
  filter: blur(13px);
  background: var(--ambient-color);
  background-size: 180% 100%;
  animation: reflected-marquee 4.2s linear infinite;
}
.ambient-strip.active .diffuse-field-wide { opacity: calc(.56 * var(--ambient-brightness)); }
.ambient-strip.active .diffuse-field-core { opacity: calc(.74 * var(--ambient-brightness)); }
.ambient-strip.breathing.active .diffuse-field, .ambient-strip.breathing.active .emitter-pixel { animation: ambient-breathe 2.8s ease-in-out infinite; }
.ambient-strip.shifting.active .diffuse-field { animation: reflected-marquee 3.6s linear infinite, ambient-shift 4.8s ease-in-out infinite; }
.ambient-strip.shifting.active .emitter-pixel { animation: pixel-chase 2.6s linear infinite; }

/* 灯带本体独立展示，不额外绘制桌板或安装卡扣。 */
.light-fixture {
  position: absolute;
  left: 50%;
  top: 50px;
  width: min(560px, 88vw);
  height: 10px;
  transform: translateX(-50%);
}
.rear-emitter {
  position: absolute;
  top: 1px;
  left: 50%;
  width: 91%;
  height: 8px;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 6px;
  box-sizing: border-box;
  overflow: hidden;
  border-radius: 999px;
  border: 1px solid #292d2c;
  background: linear-gradient(180deg, #242827, #0e1110);
  box-shadow: inset 0 1px 1px rgba(255,255,255,0.12), 0 2px 4px rgba(0,0,0,0.35);
}
.emitter-pixel {
  width: 2px;
  height: 2px;
  flex: 0 0 2px;
  border-radius: 50%;
  color: #343a39;
  background: currentColor;
  box-shadow: none;
  transition: color 0.35s ease, box-shadow 0.35s ease;
}
.ambient-strip.active .emitter-pixel {
  color: var(--ambient-color);
  animation: pixel-chase 4.2s linear infinite;
  animation-delay: calc(var(--pixel-index) * -82ms);
}
@keyframes reflected-marquee {
  from { background-position: 0% 50%; }
  to { background-position: 180% 50%; }
}
@keyframes ambient-breathe { 0%,100% { opacity:.32; filter:brightness(.58); } 50% { opacity:1; filter:brightness(1.18); } }
@keyframes ambient-shift { 0%,100% { filter:blur(18px) hue-rotate(0deg); } 50% { filter:blur(25px) hue-rotate(70deg); } }

@keyframes pixel-chase {
  0%, 100% { color: #62b7ff; box-shadow: 0 0 8px currentColor; }
  25% { color: #64dfc5; box-shadow: 0 0 8px currentColor; }
  50% { color: #ffd06d; box-shadow: 0 0 8px currentColor; }
  75% { color: #ff8b70; box-shadow: 0 0 8px currentColor; }
}

@media (prefers-reduced-motion: reduce) {
  .diffuse-field,
  .emitter-pixel { animation: none !important; }
  .ambient-strip.active .emitter-pixel { color: #67c8ff; box-shadow: 0 0 8px currentColor; }
}

@media (max-width: 760px), (orientation: landscape) and (max-height: 600px) {
  .ambient-strip {
    width: 474px;
    height: calc(94px * var(--ui-scale));
    transform: scale(var(--ui-scale));
    transform-origin: center bottom;
  }
}
</style>
