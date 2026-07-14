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
import { ChatDotRound, Camera, Cpu, Clock, DataAnalysis, ShoppingCart } from '@element-plus/icons-vue'

const route = useRoute()
defineProps({ collapsed: { type: Boolean, default: false } })
const activeMenu = computed(() => '/' + route.path.split('/')[1])
const menuItems = [
  { path: '/detection', title: '检测工作台', icon: Camera },
  { path: '/chat', title: '智能对话', icon: ChatDotRound },
  { path: '/training', title: '模型训练', icon: Cpu },
  { path: '/history', title: '历史记录', icon: Clock },
  { path: '/dashboard', title: '数据概览', icon: DataAnalysis },
  { path: '/checkout', title: '顾客结算', icon: ShoppingCart },
]
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
  -webkit-backdrop-filter: blur(24px) saturate(130%);
  transition: width .3s cubic-bezier(.2, .8, .2, 1), padding .3s cubic-bezier(.2, .8, .2, 1);

  .nav-label { padding: 0 12px 10px; color: $text-placeholder; font-size: 11px; font-weight: 600; letter-spacing: .04em; }
  .el-menu { height: auto; background: transparent; border-right: 0; }
  .el-menu-item {
    position: relative;
    height: 46px;
    margin-bottom: 4px;
    color: $sidebar-text;
    font-weight: 500;
    line-height: 46px;
    border-radius: 12px;
    transition: background .2s ease, color .2s ease;

    &.is-active {
      color: $sidebar-active-text !important;
      background: rgba(0, 113, 227, .1) !important;
      &::after { content: ''; position: absolute; right: 10px; width: 5px; height: 5px; border-radius: 50%; background: $primary-color; }
    }
    &:hover { color: $text-primary !important; background: rgba(0, 0, 0, .035) !important; }
  }

  &.collapsed {
    width: 72px;
    padding: 12px;
    .el-menu-item { justify-content: center; padding: 0 !important; span { display: none; } &::after { display: none; } }
  }
}

@media (max-width: 900px) {
  .app-sidebar { width: 72px; padding: 12px; .nav-label { display: none; } .el-menu-item { justify-content: center; padding: 0 !important; span { display: none; } &::after { display: none; } } }
}
</style>
