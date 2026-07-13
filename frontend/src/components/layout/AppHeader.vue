<template>
  <header class="app-header">
    <!-- 左侧：Logo + 平台名称 -->
    <div class="header-left">
      <el-tooltip :content="sidebarCollapsed ? '展开侧边栏' : '收起侧边栏'" placement="bottom">
        <el-button
          class="sidebar-toggle"
          :icon="sidebarCollapsed ? Expand : Fold"
          circle
          :aria-label="sidebarCollapsed ? '展开侧边栏' : '收起侧边栏'"
          @click="$emit('toggle-sidebar')"
        />
      </el-tooltip>
      <span class="brand-mark">
        <img src="/favicon.svg" alt="VisionPay" class="header-logo" />
      </span>
      <div class="brand-copy">
        <span class="header-title">VisionPay</span>
        <small>Agent Platform</small>
      </div>
    </div>
    <!-- 右侧：用户信息 + 退出按钮 -->
    <div class="header-right">
      <el-dropdown trigger="click" @command="handleCommand">
        <div class="user-info">
          <el-avatar :size="32" :src="userStore.avatar || undefined">
            {{ userStore.username?.charAt(0)?.toUpperCase() }}
          </el-avatar>
          <span class="username">{{ userStore.username }}</span>
          <el-icon><ArrowDown /></el-icon>
        </div>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="profile">
              <el-icon><User /></el-icon>个人中心
            </el-dropdown-item>
            <el-dropdown-item command="logout" divided>
              <el-icon><SwitchButton /></el-icon>退出登录
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </header>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { ArrowDown, Expand, Fold, User, SwitchButton } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
import { useUserStore } from '@/stores/user'

defineProps({
  sidebarCollapsed: {
    type: Boolean,
    default: false,
  },
})

defineEmits(['toggle-sidebar'])

const router = useRouter()
const userStore = useUserStore()

/** 处理下拉菜单命令 */
function handleCommand(command) {
  switch (command) {
    case 'profile':
      // 个人中心（后续实现）
      break
    case 'logout':
      ElMessageBox.confirm('确定要退出登录吗？', '提示', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
      }).then(() => {
        userStore.logout()
        router.push('/login')
      }).catch(() => {})
      break
  }
}
</script>

<style lang="scss" scoped>
.app-header {
  height: $header-height;
  background: rgba(255, 255, 255, 0.9);
  border-bottom: 1px solid $border-color;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 32px;
  backdrop-filter: blur(16px);
  z-index: 100;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.sidebar-toggle {
  width: 40px;
  height: 40px;
  border-color: $border-color;
  color: $text-secondary;
  background: $surface-color;
  transition: border-color 0.2s, color 0.2s, box-shadow 0.2s, transform 0.2s;

  &:hover,
  &:focus-visible {
    border-color: $primary-color;
    color: $primary-color;
    box-shadow: $ring-primary;
    transform: translateY(-1px);
  }
}

.brand-mark {
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  border-radius: $border-radius-md;
  background: $primary-color;
  box-shadow: 0 10px 24px rgba(99, 102, 241, 0.26);
}

.header-logo {
  width: 22px;
  height: 22px;
}

.brand-copy {
  display: flex;
  flex-direction: column;
  gap: 1px;

  small {
    color: $text-secondary;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }
}

.header-title {
  font-family: 'Space Grotesk', 'DM Sans', sans-serif;
  font-size: 18px;
  font-weight: 700;
  line-height: 1;
  color: $text-primary;
}

.header-right {
  display: flex;
  align-items: center;
}

.user-info {
  display: flex;
  align-items: center;
  gap: $spacing-sm;
  cursor: pointer;
  min-height: 40px;
  padding: 4px 10px 4px 4px;
  border: 1px solid $border-color;
  border-radius: $border-radius-md;
  background: $surface-color;
  transition: border-color 0.2s, box-shadow 0.2s, transform 0.2s;

  &:hover {
    border-color: $primary-color;
    box-shadow: $ring-primary;
    transform: translateY(-1px);
  }
}

.username {
  font-size: 14px;
  color: $text-primary;
  font-weight: 700;
}

@media (max-width: 720px) {
  .app-header {
    padding: 0 16px;
  }

  .brand-copy small,
  .username {
    display: none;
  }
}
</style>
