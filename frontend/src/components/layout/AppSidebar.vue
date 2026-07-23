<template>
  <aside :class="['app-sidebar', { collapsed }]">
    <router-link to="/chat" class="brand" aria-label="返回智能对话">
      <span class="brand-logo" aria-hidden="true">
        <svg viewBox="0 0 64 64" fill="none">
          <path
            d="M18 12h-4a6 6 0 0 0-6 6v8M46 12h4a6 6 0 0 1 6 6v8M18 52h-4a6 6 0 0 1-6-6v-8M46 52h4a6 6 0 0 0 6-6v-8"
            stroke="white"
            stroke-width="5"
            stroke-linecap="round"
          />
          <rect x="18" y="21" width="28" height="24" rx="7" fill="white" fill-opacity=".96" />
          <path d="M24 35h16M24 29h9" stroke="#0071E3" stroke-width="4" stroke-linecap="round" />
        </svg>
      </span>
      <span v-if="!collapsed" class="brand-name">VisionPay</span>
    </router-link>

    <el-menu
      :default-active="activeMenu"
      :router="true"
      background-color="transparent"
      :text-color="'var(--vp-sidebar-text)'"
      :active-text-color="'var(--vp-sidebar-active-text)'"
    >
      <el-tooltip
        v-for="item in menuItems"
        :key="item.path"
        :content="item.title"
        :disabled="!collapsed"
        placement="right"
        :show-arrow="false"
      >
        <el-menu-item :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.title }}</span>
        </el-menu-item>
      </el-tooltip>
    </el-menu>

    <el-tooltip
      :content="collapsed ? '展开侧边栏' : '收起侧边栏'"
      placement="right"
      :show-arrow="false"
    >
      <button
        type="button"
        :class="['sidebar-collapse', { rotated: collapsed }]"
        :aria-label="collapsed ? '展开侧边栏' : '收起侧边栏'"
        @click="$emit('update:collapsed', !collapsed)"
      >
        <el-icon><DArrowLeft /></el-icon>
      </button>
    </el-tooltip>
  </aside>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import {
  ChatDotRound,
  Cpu,
  Clock,
  DataAnalysis,
  ShoppingCart,
  PriceTag,
  Files,
  DArrowLeft,
  DArrowRight,
} from '@element-plus/icons-vue'

const route = useRoute()

defineProps({
  collapsed: {
    type: Boolean,
    default: false,
  },
})
defineEmits(['update:collapsed'])

const activeMenu = computed(() => '/' + route.path.split('/')[1])

const menuItems = computed(() => [
  { path: '/chat', title: '智能对话', icon: ChatDotRound },
  { path: '/datasets', title: '数据集版本', icon: Files },
  { path: '/training', title: '模型训练', icon: Cpu },
  { path: '/prices', title: '价目表管理', icon: PriceTag },
  { path: '/history', title: '历史记录', icon: Clock },
  { path: '/dashboard', title: '数据看板', icon: DataAnalysis },
  { path: '/checkout', title: '用户结算端', icon: ShoppingCart },
])
</script>

<style lang="scss" scoped>
.app-sidebar {
  position: relative;
  z-index: 100;
  width: $sidebar-width;
  height: 100%;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  padding: 0 12px 12px;
  background: $sidebar-bg;
  border-right: 1px solid $border-color;
  transition:
    width 0.22s ease,
    background-color 0.28s ease,
    border-color 0.28s ease;
}

html.dark .app-sidebar {
  -webkit-backdrop-filter: blur(20px) saturate(150%);
  backdrop-filter: blur(20px) saturate(150%);
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  height: $header-height;
  margin: 0 4px;
  text-decoration: none;
  border-bottom: 1px solid $border-color;
}

.brand-logo {
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  border-radius: 9px;
  background: linear-gradient(145deg, #3b8bff, #1f6fe0);

  html.dark & {
    box-shadow:
      0 4px 16px rgba(77, 141, 255, 0.42),
      inset 0 1px 0 rgba(255, 255, 255, 0.25);
  }

  svg {
    width: 17px;
    height: 17px;
  }
}

.brand-name {
  display: inline-block;
  max-width: 140px;
  overflow: hidden;
  color: $text-primary;
  font-size: 18px;
  font-weight: 700;
  letter-spacing: -0.02em;
  white-space: nowrap;
  opacity: 1;
  transition:
    max-width 0.22s ease,
    opacity 0.15s ease;
}

.el-menu {
  border-right: none;
  height: auto;
  padding-top: 12px;
  background: transparent;
}

.el-menu-item {
  position: relative;
  height: 40px;
  line-height: 40px;
  margin-bottom: 2px;
  padding: 0 12px !important;
  border-radius: 10px;
  color: $sidebar-text;
  font-size: 14px;
  font-weight: 500;
  transition:
    background 0.2s,
    color 0.2s,
    padding 0.22s ease;

  // 文字用 max-width + 透明度收进，图标在两种状态下保持同一锚点，不再跳位。
  span {
    display: inline-block;
    max-width: 160px;
    overflow: hidden;
    white-space: nowrap;
    vertical-align: middle;
    opacity: 1;
    transition:
      max-width 0.22s ease,
      opacity 0.15s ease;
  }

  .el-icon {
    font-size: 18px;
  }

  &.is-active {
    background-color: var(--vp-sidebar-active-bg) !important;
    color: $sidebar-active-text !important;
    font-weight: 600;

    // 激活项左侧渐变光条，深色下带外发光。
    &::before {
      content: '';
      position: absolute;
      left: 0;
      top: 50%;
      transform: translateY(-50%);
      width: 3px;
      height: 18px;
      border-radius: 999px;
      background: var(--vp-brand-gradient);

      html.dark & {
        box-shadow: 0 0 12px rgba(92, 157, 255, 0.55);
      }
    }
  }

  &:hover {
    background-color: var(--vp-sidebar-active-bg) !important;
    color: $sidebar-active-text !important;
  }
}

.sidebar-collapse {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  margin-top: auto;
  align-self: flex-start;
  padding: 0;
  color: $text-placeholder;
  cursor: pointer;
  background: transparent;
  border: none;
  border-radius: 8px;
  transition:
    background 0.2s,
    color 0.2s;

  .el-icon {
    transition: transform 0.22s ease;
  }
  &.rotated .el-icon {
    transform: rotate(180deg);
  }

  &:hover {
    color: $text-primary;
    background: var(--vp-sidebar-active-bg);
  }
}

.app-sidebar.collapsed {
  width: $sidebar-collapsed-width;
  padding: 0 12px 12px;

  .brand-name,
  .el-menu-item span {
    max-width: 0;
    opacity: 0;
  }
  // 折叠态把菜单项内边距平滑过渡到 10px：图标起始位置左移校正居中；
  // padding 可动画，不会像 justify-content 那样瞬移。
  .el-menu-item {
    padding: 0 10px !important;
  }
  .el-menu-item .el-icon {
    margin-right: 0;
  }
  .sidebar-collapse {
    margin-inline: 0;
  }
}

@media (max-width: 900px) {
  .app-sidebar {
    width: $sidebar-collapsed-width;
    padding: 0 12px 12px;

    .brand-name,
    .el-menu-item span {
      max-width: 0;
      opacity: 0;
    }
    .sidebar-collapse {
      margin-inline: 0;
    }
  }
}
</style>
