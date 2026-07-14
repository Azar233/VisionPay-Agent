<template>
  <div class="login-page">
    <section class="auth-hero">
      <span class="vp-kicker">Retail Vision, Simplified</span>
      <h1>让商品识别<br />更简单。</h1>
      <p>从图像到结算清单，VisionPay 将检测、训练与智能分析放进一个清晰的工作空间。</p>
      <div class="chat-preview">
        <header>
          <span class="preview-icon"><img src="/favicon.svg" alt="" /></span>
          <div><strong>VisionPay 智能助理</strong><small><i></i> 已就绪</small></div>
        </header>
        <div class="preview-body">
          <p class="bubble user">识别这批收银台商品</p>
          <p class="bubble agent">已定位 12 件商品，正在生成结算清单。</p>
          <span class="typing"><i></i><i></i><i></i></span>
        </div>
      </div>
    </section>
    <div class="login-card">
      <div class="login-header">
        <img src="/favicon.svg" alt="VisionPay" class="login-logo" />
        <h2>欢迎回来</h2>
        <p>登录后继续管理检测、训练和智能体任务</p>
      </div>
      <el-form
        ref="formRef"
        :model="loginForm"
        :rules="loginRules"
        label-width="0"
        size="large"
        @submit.prevent="handleLogin"
      >
        <el-form-item prop="username">
          <el-input
            v-model="loginForm.username"
            placeholder="请输入用户名"
            prefix-icon="User"
          />
        </el-form-item>
        <el-form-item prop="password">
          <el-input
            v-model="loginForm.password"
            type="password"
            placeholder="请输入密码"
            prefix-icon="Lock"
            show-password
            @keyup.enter="handleLogin"
          />
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            class="login-btn"
            :loading="loading"
            @click="handleLogin"
          >
            登录
          </el-button>
        </el-form-item>
      </el-form>
      <div class="login-footer">
        <span>还没有账号？</span>
        <router-link to="/register">立即注册</router-link>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const formRef = ref(null)
const loading = ref(false)

/** 登录表单数据 */
const loginForm = reactive({
  username: '',
  password: '',
})

/** 表单验证规则 */
const loginRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 50, message: '用户名长度为 3-50 个字符', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少 6 个字符', trigger: 'blur' },
  ],
}

/** 处理登录 */
async function handleLogin() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  loading.value = true
  try {
    await userStore.login({
      username: loginForm.username,
      password: loginForm.password,
    })
    ElMessage.success('登录成功')
    // 跳转到目标页面（如果有 redirect 参数）或首页
    const redirect = route.query.redirect || '/'
    router.push(redirect)
  } catch {
    // 错误已在 Axios 拦截器中统一处理
  } finally {
    loading.value = false
  }
}
</script>

<style lang="scss" scoped>
.login-page {
  width: 100%;
  min-height: 100vh;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 420px;
  align-items: center;
  justify-content: center;
  gap: 64px;
  padding: 48px max(32px, calc((100vw - 1120px) / 2));
  background:
    radial-gradient(circle at 18% 18%, rgba(0, 113, 227, .1), transparent 28%),
    linear-gradient(180deg, #fff, $bg-color 72%);
}

.auth-hero {
  max-width: 620px;

  h1 {
    margin: 24px 0 0;
    font-family: inherit;
    font-size: clamp(48px, 6vw, 72px);
    font-weight: 600;
    line-height: 1.02;
    color: $text-primary;
    letter-spacing: -.055em;
  }

  p {
    max-width: 560px;
    margin: 18px 0 0;
    color: $text-secondary;
    font-size: 18px;
    line-height: 1.7;
  }
}

.chat-preview {
  max-width: 560px;
  margin-top: 48px;
  padding: 24px;
  border: 1px solid $border-color;
  border-radius: $border-radius-lg;
  background: $surface-color;
  box-shadow: 0 24px 70px rgba(0, 0, 0, .1);
  backdrop-filter: blur(20px);

  header {
    display: flex;
    align-items: center;
    gap: 12px;
    padding-bottom: 18px;
    border-bottom: 1px solid $border-color;
  }

  strong {
    display: block;
    color: $text-primary;
    font-weight: 600;
  }

  small {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    margin-top: 3px;
    color: $success-color;
    font-weight: 500;
  }

  small i {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: $success-color;
  }
}

.preview-icon {
  width: 42px;
  height: 42px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: linear-gradient(145deg, #1688f8, #0068d4);

  img {
    width: 24px;
    height: 24px;
  }
}

.preview-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding-top: 24px;
}

.bubble {
  width: fit-content;
  max-width: 78%;
  margin: 0;
  padding: 13px 16px;
  border-radius: $border-radius-md;
  font-size: 14px;

  &.user {
    align-self: flex-end;
    color: #fff;
    background: $primary-color;
  }

  &.agent {
    color: $text-primary;
    background: $surface-muted;
  }
}

.typing {
  display: inline-flex;
  gap: 5px;
  width: fit-content;
  padding: 12px 16px;
  border-radius: $border-radius-md;
  background: $surface-muted;

  i {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: $text-secondary;
    animation: authPulse 1.2s infinite;
  }

  i:nth-child(2) {
    animation-delay: .16s;
  }

  i:nth-child(3) {
    animation-delay: .32s;
  }
}

.login-card {
  width: 420px;
  padding: 36px;
  background: rgba(255, 255, 255, .82);
  border: 1px solid $border-color;
  border-radius: $border-radius-lg;
  box-shadow: 0 24px 70px rgba(0, 0, 0, .1);
  backdrop-filter: blur(24px) saturate(130%);
}

.login-header {
  text-align: center;
  margin-bottom: 32px;

  .login-logo {
    width: 44px;
    height: 44px;
    margin-bottom: 12px;
  }

  h2 {
    font-family: inherit;
    font-size: 28px;
    color: $text-primary;
    margin-bottom: 8px;
  }

  p {
    font-size: 13px;
    color: $text-secondary;
  }
}

.login-btn {
  width: 100%;
  min-height: 48px;
}

.login-footer {
  text-align: center;
  font-size: 13px;
  color: $text-secondary;

  a {
    color: $primary-color;
    margin-left: 4px;
    font-weight: 500;

    &:hover {
      text-decoration: underline;
    }
  }
}

@keyframes authPulse {
  0%, 70%, 100% { opacity: .35; transform: translateY(0); }
  35% { opacity: 1; transform: translateY(-2px); }
}

@media (max-width: 980px) {
  .login-page {
    grid-template-columns: 1fr;
    gap: 28px;
    padding: 32px 20px;
  }

  .auth-hero {
    text-align: center;

    h1 {
      font-size: 40px;
    }

    p {
      margin-left: auto;
      margin-right: auto;
      font-size: 16px;
    }
  }

  .chat-preview {
    margin: 28px auto 0;
  }

  .login-card {
    width: min(100%, 420px);
    justify-self: center;
  }
}
</style>
