<template>
  <article class="chapter recognition">
    <div class="scan-frame">
      <i class="scan-frame__corner tl"></i><i class="scan-frame__corner tr"></i>
      <i class="scan-frame__corner bl"></i><i class="scan-frame__corner br"></i>
      <i class="scan-frame__sweep"></i>
      <div class="scan-frame__boxes">
        <b
          v-for="(item, index) in products"
          :key="item.name"
          :class="{ locked: progress >= (index + 1) / (products.length + 1) || ready }"
          :style="{
            '--index': index,
            '--x': item.x + '%',
            '--y': item.y + '%',
            '--w': item.w + '%',
            '--h': item.h + '%',
          }"
        >
          <em></em>
          <u class="scan-frame__emoji" aria-hidden="true">{{ item.emoji }}</u>
          <small>{{ item.name }} · ¥{{ item.price }}</small>
        </b>
      </div>
    </div>
    <div>
      <span>02 / I CAN SEE</span>
      <h1>I understand every product.</h1>
      <p>货架上的每一件商品都会被实时框选、识别并标好价格，无需人工逐件核对。</p>
    </div>
  </article>
</template>

<script setup>
defineProps({ progress: { type: Number, default: 0 }, ready: Boolean })
const products = [
  { name: 'Milk', price: '12.90', x: 5, y: 3, w: 90, h: 24, emoji: '🥛' },
  { name: 'Coffee', price: '18.00', x: 5, y: 37, w: 90, h: 24, emoji: '☕' },
  { name: 'Snack', price: '8.50', x: 5, y: 71, w: 90, h: 24, emoji: '🍪' },
]
</script>

<style lang="scss" scoped>
@use './chapter';
</style>
