<template>
  <div class="main-layout">
    <!-- 顶部导航栏 -->
    <AppHeader
      :sidebar-collapsed="sidebarCollapsed"
      @toggle-sidebar="toggleSidebar"
    />
    <!-- 下方区域：侧边栏 + 内容区 -->
    <div class="layout-body">
      <AppSidebar :collapsed="sidebarCollapsed" />
      <!-- 页面内容区 -->
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

function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value
}
</script>

<style lang="scss" scoped>
.main-layout {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: $bg-color;
}

.layout-body {
  flex: 1;
  display: flex;
  overflow: hidden;
  min-height: 0;
  padding: 16px;
  gap: 16px;
}

.layout-content {
  flex: 1;
  min-width: 0;
  background: $bg-color;
  overflow-y: auto;
  padding: 0;
  border-radius: $border-radius-md;
}

@media (max-width: 900px) {
  .layout-body {
    padding: 10px;
    gap: 10px;
  }
}
</style>
