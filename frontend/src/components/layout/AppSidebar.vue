<template>
  <aside :class="['app-sidebar', { collapsed }]">
    <el-menu
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

/** 侧边栏菜单配置 */
const menuItems = [
  { path: '/detection', title: '检测工作台', icon: Camera },
  { path: '/chat', title: '智能对话', icon: ChatDotRound },
  { path: '/training', title: '模型训练', icon: Cpu },
  { path: '/history', title: '历史记录', icon: Clock },
  { path: '/dashboard', title: '数据看板', icon: DataAnalysis },
  { path: '/customer-side', title: '用户侧跳转', icon: Connection },
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
</style>
