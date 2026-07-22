<template>
  <section class="reduced-story">
    <article v-for="chapter in chapters" :key="chapter.title">
      <span>{{ chapter.index }}</span>
      <h2>{{ chapter.title }}</h2>
      <p>{{ chapter.copy }}</p>
    </article>
  </section>
</template>

<script setup>
const chapters = [
  { index: '01', title: "HELLO. I'M VICO.", copy: 'VisionPay AI Retail Operating System.' },
  {
    index: '02',
    title: 'I understand every product.',
    copy: '货架上的每一件商品都会被实时框选、识别并标好价格。',
  },
  {
    index: '03',
    title: 'One mission. Five minds.',
    copy: '识别、数据、训练、目录与知识库五位 Agent 协作完成每一个任务。',
  },
]
</script>

<style lang="scss" scoped>
.reduced-story {
  display: grid;
  gap: 12px;
  width: min(100%, 560px);
}
article {
  padding: 18px;
  border: 1px solid $vj-glass-border;
  border-radius: 16px;
  background: $vj-glass-bg;
}
span {
  color: $agent-detection;
  font-size: 10px;
  font-weight: 800;
}
h2 {
  margin: 7px 0;
  font-size: 23px;
}
p {
  margin: 0;
  color: $vj-text-soft;
  font-size: 13px;
}
</style>
