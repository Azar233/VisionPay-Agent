<template>
  <header class="app-header">
    <div class="header-left">
      <el-tooltip :content="sidebarCollapsed ? '展开侧边栏' : '收起侧边栏'" placement="bottom" :show-arrow="false">
        <el-button
          class="sidebar-toggle"
          :icon="sidebarCollapsed ? Expand : Fold"
          circle
          :aria-label="sidebarCollapsed ? '展开侧边栏' : '收起侧边栏'"
          @click="$emit('toggle-sidebar')"
        />
      </el-tooltip>
      <router-link to="/detection" class="brand-mark" aria-label="返回检测工作台">
        <img src="/favicon.svg" alt="" class="header-logo" />
      </router-link>
      <div class="brand-copy">
        <span class="header-title">VisionPay</span>
        <small>Retail Intelligence</small>
      </div>
    </div>

    <div class="header-right">
      <el-dropdown
        trigger="click"
        placement="bottom-end"
        :offset="8"
        :show-arrow="false"
        popper-class="user-menu-popper"
        @command="handleCommand"
      >
        <div class="user-info" aria-label="打开用户菜单">
          <el-avatar :size="34" :src="userStore.avatar || undefined">
            {{ userStore.username?.charAt(0)?.toUpperCase() }}
          </el-avatar>
          <span class="username">{{ userStore.username }}</span>
          <el-icon><ArrowDown /></el-icon>
        </div>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="theme" class="theme-menu-item">
              <el-icon><Sunny v-if="isDark" /><Moon v-else /></el-icon>
              <span class="theme-menu-label">{{ themeLabel }}</span>
              <span :class="['theme-switch', { active: isDark }]" aria-hidden="true"><i></i></span>
            </el-dropdown-item>
            <el-dropdown-item command="profile"><el-icon><User /></el-icon>个人中心</el-dropdown-item>
            <el-dropdown-item command="logout" divided><el-icon><SwitchButton /></el-icon>退出登录</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </header>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { ArrowDown, Expand, Fold, Moon, Sunny, User, SwitchButton } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
import { useUserStore } from '@/stores/user'
import { useTheme } from '@/composables/useTheme'

defineProps({ sidebarCollapsed: { type: Boolean, default: false } })
defineEmits(['toggle-sidebar'])
const router = useRouter()
const userStore = useUserStore()
const { isDark, themeLabel, toggleTheme } = useTheme()

function handleCommand(command) {
  if (command === 'theme') {
    toggleTheme()
    return
  }
  if (command === 'logout') {
    ElMessageBox.confirm('确定要退出登录吗？', '退出登录', {
      confirmButtonText: '退出', cancelButtonText: '取消', type: 'warning',
    }).then(() => { userStore.logout(); router.push('/login') }).catch(() => {})
  }
}
</script>

<style lang="scss" scoped>
.app-header {
  z-index: 100;
  height: $header-height;
  padding: 0 28px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: rgba(245, 245, 247, .78);
  border-bottom: 1px solid $border-color;
  backdrop-filter: blur(24px) saturate(150%);
  -webkit-backdrop-filter: blur(24px) saturate(150%);
}

.header-left, .header-right, .user-info { display: flex; align-items: center; }
.header-left { gap: 10px; }

.sidebar-toggle {
  width: 40px;
  height: 40px;
  color: $text-secondary;
  background: transparent;
  border-color: transparent;
  box-shadow: none;

  &:hover, &:focus-visible {
    color: $text-primary;
    background: rgba(255, 255, 255, .82);
    border-color: $border-color;
    box-shadow: $shadow-sm;
  }
}

.brand-mark {
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  border-radius: 12px;
  background: linear-gradient(145deg, #1688f8, #0068d4);
  box-shadow: 0 8px 22px rgba(0, 113, 227, .22), inset 0 1px rgba(255, 255, 255, .35);
}
.header-logo { width: 24px; height: 24px; }
.brand-copy { display: flex; flex-direction: column; gap: 2px; }
.header-title { color: $text-primary; font-size: 17px; font-weight: 600; line-height: 1; letter-spacing: -.02em; }
.brand-copy small { color: $text-secondary; font-size: 10px; font-weight: 400; }

.user-info {
  gap: 8px;
  min-height: 44px;
  padding: 4px 12px 4px 4px;
  color: $text-secondary;
  cursor: pointer;
  background: rgba(255, 255, 255, .68);
  border: 1px solid $border-color;
  border-radius: 999px;
  transition: background .2s ease, border-color .2s ease, box-shadow .2s ease;

  &:hover { background: #fff; border-color: $border-strong; box-shadow: $shadow-sm; }
}
.username { color: $text-primary; font-size: 14px; font-weight: 500; }

:global(.user-menu-popper.el-popper) {
  width: 208px !important;
  min-width: 208px !important;
  margin-left: -12px !important;
  padding: 0 !important;
  overflow: hidden;
  border: 1px solid var(--vp-border) !important;
  border-radius: 16px !important;
  background: var(--vp-surface) !important;
  box-shadow: 0 18px 48px rgba(0, 0, 0, .18) !important;
  backdrop-filter: blur(24px) saturate(140%);
}
:global(.user-menu-popper .el-popper__arrow) { display: none !important; }
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
  border-radius: 10px;
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
:global(.user-menu-popper .theme-menu-item) { display: grid; grid-template-columns: 17px minmax(0, 1fr) auto; }
:global(.user-menu-popper .theme-menu-label) { white-space: nowrap; }
:global(.user-menu-popper .theme-switch) {
  width: 32px;
  height: 18px;
  display: flex;
  align-items: center;
  padding: 2px;
  border-radius: 999px;
  background: #d2d2d7;
  transition: background .25s ease;
}
:global(.user-menu-popper .theme-switch i) {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, .2);
  transition: transform .25s cubic-bezier(.2, .8, .2, 1);
}
:global(.user-menu-popper .theme-switch.active) { background: #0a84ff; }
:global(.user-menu-popper .theme-switch.active i) { transform: translateX(14px); }

@media (max-width: 720px) {
  .app-header { padding: 0 16px; }
  .brand-copy small, .username { display: none; }
}
</style>
