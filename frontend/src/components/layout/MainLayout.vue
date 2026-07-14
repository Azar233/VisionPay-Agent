<template>
  <div class="main-layout">
    <AppHeader :sidebar-collapsed="sidebarCollapsed" @toggle-sidebar="toggleSidebar" />
    <div class="layout-body">
      <AppSidebar :collapsed="sidebarCollapsed" />
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
function toggleSidebar() { sidebarCollapsed.value = !sidebarCollapsed.value }
</script>

<style lang="scss" scoped>
.main-layout {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background:
    radial-gradient(circle at 84% -10%, rgba(0, 113, 227, .08), transparent 28%),
    $bg-color;
}

.layout-body {
  min-height: 0;
  flex: 1;
  display: flex;
  gap: 24px;
  padding: 16px 24px 24px;
  overflow: hidden;
}

.layout-content {
  min-width: 0;
  flex: 1;
  overflow-y: auto;
  background: transparent;
  border-radius: $border-radius-lg;
}

@media (max-width: 900px) {
  .layout-body { gap: 12px; padding: 12px 12px 16px; }
}
</style>
