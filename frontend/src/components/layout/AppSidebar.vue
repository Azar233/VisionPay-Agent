<template>
  <aside :class="['app-sidebar', { collapsed }]">
    <!-- 桌面端侧边栏 -->
    <el-menu
      class="desktop-menu"
      :default-active="activeMenu"
      :router="true"
      background-color="transparent"
      text-color="#6b7280"
      active-text-color="#4f46e5"
    >
      <el-tooltip
        v-for="item in menuItems"
        :key="item.path"
        :content="item.title"
        :disabled="!collapsed"
        placement="right"
      >
        <el-menu-item :index="item.path">
          <el-icon>
            <component :is="item.icon" />
          </el-icon>
          <span>{{ item.title }}</span>
        </el-menu-item>
      </el-tooltip>
    </el-menu>

    <!-- 手机端底部导航 -->
    <nav class="mobile-bottom-nav">
      <router-link
        v-for="item in menuItems"
        :key="item.path"
        :to="item.path"
        :class="['bottom-nav-item', { active: activeMenu === item.path }]"
      >
        <el-icon><component :is="item.icon" /></el-icon>
        <span>{{ item.shortTitle }}</span>
      </router-link>
    </nav>
  </aside>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import {
  ChatDotRound,
  Camera,
  Cpu,
  Clock,
  Connection,
  DataAnalysis,
} from '@element-plus/icons-vue'

const route = useRoute()

defineProps({
  collapsed: {
    type: Boolean,
    default: false,
  },
})

/** 当前激活的菜单项 */
const activeMenu = computed(() => {
  return '/' + route.path.split('/')[1]
})

/** 侧边栏菜单配置。
 * title 用于桌面端侧边栏，shortTitle 用于手机端底部导航。
 * 注意：main 分支已将 /checkout 拆分为独立 Vite 应用，开发者后台不再包含该路由。
 */
const menuItems = [
  { path: '/detection', title: '检测工作台', shortTitle: '检测', icon: Camera },
  { path: '/chat', title: '智能对话', shortTitle: '对话', icon: ChatDotRound },
  { path: '/training', title: '模型训练', shortTitle: '训练', icon: Cpu },
  { path: '/history', title: '历史记录', shortTitle: '历史', icon: Clock },
  { path: '/dashboard', title: '数据看板', shortTitle: '看板', icon: DataAnalysis },
  { path: '/customer-side', title: '用户侧跳转', shortTitle: '用户侧', icon: Connection },
]
</script>

<style lang="scss" scoped>
.app-sidebar {
  width: $sidebar-width;
  height: 100%;
  background: $sidebar-bg;
  border: 1px solid $border-color;
  border-radius: $border-radius-md;
  box-shadow: $shadow-sm;
  overflow-y: auto;
  padding: 10px;
  flex-shrink: 0;
  transition: width 0.22s ease, padding 0.22s ease;

  .el-menu {
    border-right: none;
    height: auto;
    background: transparent;
  }

  .el-menu-item {
    height: 44px;
    line-height: 44px;
    margin-bottom: 6px;
    border-radius: $border-radius-md;
    color: $sidebar-text;
    font-weight: 700;
    transition: background 0.2s, color 0.2s, transform 0.2s;

    &.is-active {
      background-color: $primary-soft !important;
      color: $sidebar-active-text !important;
    }

    &:hover {
      background-color: #f5f6fb !important;
      color: $text-primary !important;
      transform: translateX(2px);
    }
  }

  &.collapsed {
    width: 68px;
    padding: 8px;

    .el-menu-item {
      justify-content: center;
      padding: 0 !important;

      span {
        display: none;
      }
    }
  }
}

.mobile-bottom-nav {
  display: none;
}

.bottom-nav-item {
  flex: 1 1 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  height: 100%;
  min-width: 0;
  padding: 0 2px;
  color: $text-secondary;
  text-decoration: none;
  font-size: 9px;
  font-weight: 700;
  line-height: 1.1;
  white-space: nowrap;
  transition: color 0.2s, background 0.2s;

  .el-icon {
    font-size: 18px;
  }

  span {
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 100%;
  }

  &.active {
    color: $primary-color;
    background: $primary-soft;
  }
}

@media (max-width: 900px) {
  .app-sidebar {
    width: 68px;
    padding: 8px;

    .el-menu-item {
      justify-content: center;
      padding: 0 !important;

      span {
        display: none;
      }
    }
  }
}

@media (max-width: 640px) {
  .app-sidebar {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    width: 100%;
    height: 64px;
    border-radius: 0;
    border: 0;
    border-top: 1px solid $border-color;
    z-index: 1000;
    padding: 0;
    overflow: visible;
    background: $surface-color;
  }

  .desktop-menu {
    display: none;
  }

  .mobile-bottom-nav {
    display: flex;
    align-items: center;
    height: 100%;
  }
}
</style>
