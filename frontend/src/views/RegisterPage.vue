<template>
  <div class="register-page">
    <section class="auth-hero">
      <span class="vp-kicker">VisionPay Workspace</span>
      <h1>一个账号，<br />开启智能零售。</h1>
      <p>创建账号后即可使用商品检测、模型训练和智能分析工作台。</p>
      <div class="feature-grid">
        <span><strong>YOLOv11</strong><small>商品定位</small></span>
        <span><strong>Agent</strong><small>结果分析</small></span>
        <span><strong>Metrics</strong><small>训练监控</small></span>
      </div>
    </section>
    <div class="register-card">
      <div class="register-header">
        <img src="/favicon.svg" alt="logo" class="register-logo" />
        <h2>创建账号</h2>
        <p>开始使用 VisionPay 智能检测平台</p>
      </div>
      <el-form
        ref="formRef"
        :model="registerForm"
        :rules="registerRules"
        label-width="0"
        size="large"
        @submit.prevent="handleRegister"
      >
        <el-form-item prop="username">
          <el-input
            v-model="registerForm.username"
            placeholder="请输入用户名"
            prefix-icon="User"
          />
        </el-form-item>
        <el-form-item prop="email">
          <el-input
            v-model="registerForm.email"
            placeholder="请输入邮箱"
            prefix-icon="Message"
          />
        </el-form-item>
        <el-form-item prop="password">
          <el-input
            v-model="registerForm.password"
            type="password"
            placeholder="请输入密码（至少 6 位）"
            prefix-icon="Lock"
            show-password
          />
        </el-form-item>
        <el-form-item prop="confirmPassword">
          <el-input
            v-model="registerForm.confirmPassword"
            type="password"
            placeholder="请确认密码"
            prefix-icon="Lock"
            show-password
            @keyup.enter="handleRegister"
          />
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            class="register-btn"
            :loading="loading"
            @click="handleRegister"
          >
            创建账号
          </el-button>
        </el-form-item>
      </el-form>
      <div class="register-footer">
        <span>已有账号？</span>
        <router-link to="/login">立即登录</router-link>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { registerApi } from '@/api/auth'

const router = useRouter()
const formRef = ref(null)
const loading = ref(false)

/** 注册表单数据 */
const registerForm = reactive({
  username: '',
  email: '',
  password: '',
  confirmPassword: '',
})

/** 确认密码验证器 */
const validateConfirmPassword = (rule, value, callback) => {
  if (value !== registerForm.password) {
    callback(new Error('两次输入的密码不一致'))
  } else {
    callback()
  }
}

/** 表单验证规则 */
const registerRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 50, message: '用户名长度为 3-50 个字符', trigger: 'blur' },
  ],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '请输入有效的邮箱地址', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少 6 个字符', trigger: 'blur' },
  ],
  confirmPassword: [
    { required: true, message: '请确认密码', trigger: 'blur' },
    { validator: validateConfirmPassword, trigger: 'blur' },
  ],
}

/** 处理注册 */
async function handleRegister() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  loading.value = true
  try {
    await registerApi({
      username: registerForm.username,
      email: registerForm.email,
      password: registerForm.password,
    })
    ElMessage.success('注册成功，请登录')
    router.push('/login')
  } catch {
    // 错误已在 Axios 拦截器中统一处理
  } finally {
    loading.value = false
  }
}
</script>

<style lang="scss" scoped>
.register-page {
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
  max-width: 610px;

  h1 {
    margin: 24px 0 0;
    font-family: inherit;
    font-size: clamp(46px, 6vw, 70px);
    font-weight: 600;
    line-height: 1.04;
    color: $text-primary;
    letter-spacing: -.05em;
  }

  p {
    margin: 18px 0 0;
    color: $text-secondary;
    font-size: 18px;
    line-height: 1.7;
  }
}

.feature-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-top: 40px;

  span {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 18px;
    border: 1px solid $border-color;
    border-radius: $border-radius-md;
    background: $surface-color;
    box-shadow: $shadow-sm;
  }

  strong {
    color: $text-primary;
    font-size: 18px;
  }

  small {
    color: $text-secondary;
    font-size: 13px;
  }
}

.register-card {
  width: 420px;
  padding: 36px;
  background: rgba(255, 255, 255, .82);
  border: 1px solid $border-color;
  border-radius: $border-radius-lg;
  box-shadow: 0 24px 70px rgba(0, 0, 0, .1);
  backdrop-filter: blur(24px) saturate(130%);
}

.register-header {
  text-align: center;
  margin-bottom: 32px;

  .register-logo {
    width: 48px;
    height: 48px;
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

.register-btn {
  width: 100%;
  min-height: 48px;
}

.register-footer {
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

@media (max-width: 980px) {
  .register-page {
    grid-template-columns: 1fr;
    gap: 28px;
    padding: 32px 20px;
  }

  .auth-hero {
    text-align: center;

    h1 {
      font-size: 38px;
    }
  }

  .feature-grid {
    max-width: 520px;
    margin-left: auto;
    margin-right: auto;
  }

  .register-card {
    width: min(100%, 420px);
    justify-self: center;
  }
}

@media (max-width: 560px) {
  .feature-grid {
    grid-template-columns: 1fr;
  }
}
</style>
