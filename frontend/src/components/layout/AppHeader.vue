<template>
  <header class="app-header">
    <div class="header-left">
      <h1 class="page-title">{{ pageTitle }}</h1>
      <el-popover
        v-if="pageDescription"
        trigger="click"
        placement="bottom-start"
        :width="320"
        :show-arrow="false"
        :offset="8"
      >
        <template #reference>
          <button class="page-info-button" type="button" aria-label="查看页面说明">
            <el-icon><InfoFilled /></el-icon>
          </button>
        </template>
        <p class="page-info-text">{{ pageDescription }}</p>
      </el-popover>
    </div>

    <div class="header-right">
      <el-button
        v-if="canEnterCustomerMode"
        class="customer-mode-entry"
        type="primary"
        :icon="FullScreen"
        @click="enterCustomerMode"
      >
        进入顾客模式
      </el-button>
      <el-dropdown
        trigger="click"
        placement="bottom-end"
        :offset="8"
        :show-arrow="false"
        popper-class="user-menu-popper"
        @command="handleCommand"
      >
        <div class="user-info" aria-label="打开用户菜单">
          <el-avatar :size="32" :src="userStore.avatar || undefined">
            {{ userStore.displayName?.charAt(0)?.toUpperCase() }}
          </el-avatar>
          <span class="username">{{ userStore.displayName }}</span>
          <el-icon><ArrowDown /></el-icon>
        </div>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="theme" class="theme-menu-item">
              <el-icon><Sunny v-if="isDark" /><Moon v-else /></el-icon>
              <span class="theme-menu-label">{{ themeLabel }}</span>
              <span :class="['theme-switch', { active: isDark }]" aria-hidden="true"><i></i></span>
            </el-dropdown-item>
            <el-dropdown-item command="profile"
              ><el-icon><User /></el-icon>个人中心</el-dropdown-item
            >
            <el-dropdown-item command="logout" divided
              ><el-icon><SwitchButton /></el-icon>退出登录</el-dropdown-item
            >
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </header>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowDown,
  FullScreen,
  InfoFilled,
  Moon,
  Sunny,
  SwitchButton,
  User,
} from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
import { useCustomerModeStore } from '@/stores/customerMode'
import { useUserStore } from '@/stores/user'
import { useTheme } from '@/composables/useTheme'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const customerModeStore = useCustomerModeStore()
const { isDark, themeLabel, toggleTheme } = useTheme()

const pageTitle = computed(() => route.meta?.title || 'VisionPay')
const pageDescription = computed(() => route.meta?.description || '')
const canEnterCustomerMode = computed(
  () => route.name === 'CustomerCheckout' && !customerModeStore.isActiveFor(userStore.user?.id),
)

async function enterCustomerMode() {
  customerModeStore.enter(userStore.user?.id)
  await document.documentElement.requestFullscreen?.().catch(() => {})
}

function handleCommand(command) {
  if (command === 'theme') {
    toggleTheme()
    return
  }
  if (command === 'profile') {
    router.push('/settings')
    return
  }
  if (command === 'logout') {
    ElMessageBox.confirm('确定要退出登录吗？', '退出登录', {
      confirmButtonText: '退出',
      cancelButtonText: '取消',
      type: 'warning',
      customClass: 'app-confirm-dialog',
    })
      .then(() => {
        userStore.logout()
        router.push({ path: '/welcome', query: { entry: 'core' } })
      })
      .catch(() => {})
  }
}
</script>

<style lang="scss" scoped>
.app-header {
  z-index: 90;
  height: $header-height;
  flex-shrink: 0;
  padding: 0 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: $surface-color;
  border-bottom: 1px solid $border-color;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.page-title {
  margin: 0;
  color: $text-primary;
  font-size: 17px;
  font-weight: 600;
}

.page-info-button {
  width: 14px;
  height: 14px;
  display: grid;
  place-items: center;
  align-self: flex-start;
  margin-top: 2px;
  padding: 0;
  border: 0;
  color: $text-placeholder;
  background: transparent;
  font-size: 12px;
  cursor: pointer;
  transition: color 0.2s ease;

  &:hover {
    color: $primary-color;
  }
}

.page-info-text {
  margin: 0;
  color: $text-secondary;
  font-size: 13px;
  line-height: 1.7;
}

.header-right,
.user-info {
  display: flex;
  align-items: center;
}

.header-right {
  gap: 12px;
}

.customer-mode-entry {
  min-height: 40px;
  padding: 0 18px;
  border-radius: 999px;
  font-weight: 700;
}

.user-info {
  gap: 8px;
  min-height: 40px;
  padding: 4px 8px 4px 4px;
  color: $text-secondary;
  cursor: pointer;
  border-radius: 999px;
  transition: background 0.2s ease;

  &:hover {
    background: var(--vp-sidebar-active-bg);
  }
}
.username {
  color: $text-primary;
  font-size: 14px;
  font-weight: 500;
}

:global(.user-menu-popper.el-popper) {
  width: 208px !important;
  min-width: 208px !important;
  margin-left: -12px !important;
  padding: 0 !important;
  overflow: hidden;
  border: 1px solid var(--vp-border) !important;
  border-radius: 14px !important;
  background: var(--vp-surface) !important;
  box-shadow: var(--vp-shadow-lg) !important;
}
:global(.user-menu-popper .el-popper__arrow) {
  display: none !important;
}
:global(.user-menu-popper .el-dropdown-menu) {
  width: 100%;
  min-width: 0;
  padding: 5px;
  border-radius: inherit;
  background: transparent;
}
:global(.user-menu-popper .el-dropdown-menu__item) {
  min-height: 38px;
  padding: 0 10px;
  gap: 8px;
  border-radius: 9px;
  color: var(--vp-text);
  font-size: 14px;
}
:global(.user-menu-popper .el-dropdown-menu__item:hover),
:global(.user-menu-popper .el-dropdown-menu__item:focus) {
  color: var(--vp-text) !important;
  background: var(--vp-surface-muted) !important;
}
:global(.user-menu-popper .el-dropdown-menu__item:focus-visible) {
  outline: none !important;
  box-shadow: inset 0 0 0 1px var(--vp-border-strong);
}
:global(.user-menu-popper .el-dropdown-menu__item--divided) {
  margin-top: 4px;
  border-top-color: var(--vp-border);
}
:global(.user-menu-popper .theme-menu-item) {
  display: grid;
  grid-template-columns: 17px minmax(0, 1fr) auto;
}
:global(.user-menu-popper .theme-menu-label) {
  white-space: nowrap;
}
:global(.user-menu-popper .theme-switch) {
  width: 32px;
  height: 18px;
  display: flex;
  align-items: center;
  padding: 2px;
  border-radius: 999px;
  background: #d2d2d7;
  transition: background 0.25s ease;
}
:global(.user-menu-popper .theme-switch i) {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
  transition: transform 0.25s cubic-bezier(0.2, 0.8, 0.2, 1);
}
:global(.user-menu-popper .theme-switch.active) {
  background: var(--vp-primary);
}
:global(.user-menu-popper .theme-switch.active i) {
  transform: translateX(14px);
}

@media (max-width: 720px) {
  .app-header {
    padding: 0 16px;
  }
  .username {
    display: none;
  }
}
</style>
