<template>
  <div class="main-layout">
    <AppSidebar :collapsed="sidebarCollapsed" @update:collapsed="sidebarCollapsed = $event" />
    <div class="layout-main">
      <AppHeader />
      <main class="layout-content">
        <router-view />
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import AppHeader from './AppHeader.vue'
import AppSidebar from './AppSidebar.vue'

const sidebarCollapsed = ref(false)
</script>

<style lang="scss" scoped>
.main-layout {
  width: 100%;
  height: 100%;
  display: flex;
  /* 透明底色让 body 上的极光背景层透出来（深色主视觉）。 */
  background: transparent;
}

.layout-main {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
}

.layout-content {
  min-height: 0;
  flex: 1;
  overflow-y: auto;
  background: transparent;
}
</style>
