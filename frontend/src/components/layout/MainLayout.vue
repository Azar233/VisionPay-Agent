<template>
  <div :class="['main-layout', { 'is-customer-mode': customerModeActive }]">
    <AppSidebar
      v-if="!customerModeActive"
      :collapsed="sidebarCollapsed"
      @update:collapsed="sidebarCollapsed = $event"
    />
    <div class="layout-main">
      <AppHeader v-if="!customerModeActive" />
      <CustomerModeExitControl v-if="customerModeActive" />
      <main :class="['layout-content', { 'customer-mode-content': customerModeActive }]">
        <router-view />
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import CustomerModeExitControl from '@/components/checkout/CustomerModeExitControl.vue'
import { useCustomerModeStore } from '@/stores/customerMode'
import { useUserStore } from '@/stores/user'
import AppHeader from './AppHeader.vue'
import AppSidebar from './AppSidebar.vue'

const sidebarCollapsed = ref(false)
const userStore = useUserStore()
const customerModeStore = useCustomerModeStore()
const customerModeActive = computed(() => customerModeStore.isActiveFor(userStore.user?.id))
</script>

<style lang="scss" scoped>
.main-layout {
  width: 100%;
  height: 100%;
  display: flex;
  background: $bg-color;
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

.main-layout.is-customer-mode {
  width: 100%;
  height: 100%;
  overflow: hidden;
}

.customer-mode-content {
  position: relative;
  width: 100%;
  height: 100%;
  overflow-y: auto;
  background: $bg-color;
}
</style>
