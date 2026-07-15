<template>
  <aside :class="['app-sidebar', { collapsed }]">
    <p v-if="!collapsed" class="nav-label">工作空间</p>
    <el-menu :default-active="activeMenu" :router="true" background-color="transparent" text-color="#6e6e73" active-text-color="#1d1d1f">
      <el-tooltip v-for="item in menuItems" :key="item.path" :content="item.title" :disabled="!collapsed" placement="right" :show-arrow="false">
        <el-menu-item :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.title }}</span>
        </el-menu-item>
      </el-tooltip>
    </el-menu>
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
  DataAnalysis,
  ShoppingCart,
  PriceTag,
  Files,
} from '@element-plus/icons-vue'

const route = useRoute()

defineProps({
  collapsed: {
    type: Boolean,
    default: false,
  },
})

const activeMenu = computed(() => '/' + route.path.split('/')[1])

const menuItems = computed(() => [
  { path: '/detection', title: '检测工作台', icon: Camera },
  { path: '/chat', title: '智能对话', icon: ChatDotRound },
  { path: '/training', title: '模型训练', icon: Cpu },
  { path: '/datasets', title: '数据集版本', icon: Files },
  { path: '/history', title: '历史记录', icon: Clock },
  { path: '/dashboard', title: '数据概览', icon: DataAnalysis },
  { path: '/checkout', title: '顾客结算', icon: ShoppingCart },
  { path: '/prices', title: '价目表管理', icon: PriceTag },
])
</script>

<style lang="scss" scoped>
.app-sidebar {
  width: $sidebar-width;
  height: 100%;
  flex-shrink: 0;
  padding: 16px 12px;
  overflow-y: auto;
  background: $sidebar-bg;
  border: 1px solid $border-color;
  border-radius: $border-radius-md;
  box-shadow: 0 12px 40px rgba(0, 0, 0, .04);
  backdrop-filter: blur(24px) saturate(130%);
  transition: width 0.22s ease, padding 0.22s ease;

  .nav-label {
    margin: 0 0 8px 12px;
    font-size: 12px;
    font-weight: 600;
    color: #9ca3af;
    letter-spacing: 0.05em;
  }

  .el-menu {
    border-right: none;
    height: auto;
    background: transparent;
  }

  .el-menu-item {
    height: 44px;
    line-height: 44px;
    margin-bottom: 4px;
    border-radius: $border-radius-md;
    color: $sidebar-text;
    font-weight: 600;
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
    padding: 16px 8px;

    .el-menu-item {
      justify-content: center;
      padding: 0 !important;

      span {
        display: none;
      }
    }
  }
}

@media (max-width: 900px) {
  .app-sidebar {
    width: 68px;
    padding: 16px 8px;

    .el-menu-item {
      justify-content: center;
      padding: 0 !important;

      span {
        display: none;
      }
    }
  }
}
</style>
