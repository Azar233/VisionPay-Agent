<template>
  <section
    class="holo-login"
    :data-projection-anchor="projectionAnchor"
    aria-label="Vision 全息登录投影"
  >
    <div class="holo-login__beam" aria-hidden="true"><i class="holo-login__source"></i></div>
    <div class="holo-login__panel">
      <div class="holo-login__grid" aria-hidden="true"></div>
      <span class="holo-login__kicker">VISIONPAY CORE</span>
      <h1 class="holo-login__brand">VisionPay</h1>
      <h2>{{ authenticated ? '工作区已准备就绪' : '身份投影验证' }}</h2>
      <p v-if="authenticated">无需重新输入账号密码，可直接返回 Workspace。</p>
      <el-button
        v-if="authenticated"
        type="primary"
        class="holo-login__submit"
        @click="$emit('return-workspace')"
      >
        返回 Workspace
      </el-button>
      <template v-else>
        <el-form
          ref="formRef"
          :model="loginForm"
          :rules="loginRules"
          label-width="0"
          size="large"
          @submit.prevent="handleLogin"
        >
          <el-form-item prop="username">
            <el-input v-model="loginForm.username" placeholder="请输入用户名" prefix-icon="User" />
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
          <el-button
            type="primary"
            native-type="submit"
            class="holo-login__submit"
            :loading="loading"
          >
            进入 VisionPay
          </el-button>
        </el-form>
        <p class="holo-login__footer">
          还没有账号？<router-link to="/register">立即注册</router-link>
        </p>
      </template>
    </div>
  </section>
</template>

<script setup>
import { useLoginForm } from '@/composables/useLoginForm'

defineProps({
  authenticated: { type: Boolean, default: false },
  projectionAnchor: { type: String, default: 'vision-chest' },
})
const emit = defineEmits(['authenticated', 'return-workspace'])
const { formRef, loading, loginForm, loginRules, handleLogin } = useLoginForm({
  onSuccess: (context) => emit('authenticated', context),
})
</script>

<style lang="scss" scoped>
.holo-login {
  position: relative;
  z-index: 4;
  width: min(100%, 410px);
  padding-top: 196px;
}
.holo-login__beam {
  position: absolute;
  z-index: -1;
  top: -148px;
  left: 50%;
  width: min(320px, 84vw);
  height: 344px;
  clip-path: polygon(48.5% 0, 51.5% 0, 100% 100%, 0 100%);
  background: linear-gradient(
    to bottom,
    color-mix(in srgb, #fff 96%, $agent-detection) 0%,
    color-mix(in srgb, $agent-detection 68%, white) 8%,
    color-mix(in srgb, $agent-detection 42%, transparent) 28%,
    color-mix(in srgb, $agent-detection 24%, transparent) 52%,
    color-mix(in srgb, $agent-detection 10%, transparent) 78%,
    transparent 100%
  );
  opacity: clamp(0, calc((var(--login-reveal, 1) - 0.42) * 2.2), 1);
  transform: translateX(-50%) scaleY(clamp(0.01, calc((var(--login-reveal, 1) - 0.49) * 2.14), 1));
  transform-origin: center bottom;
  backface-visibility: hidden;
  will-change: transform, opacity;
}
.holo-login__source {
  position: absolute;
  top: -2px;
  left: 50%;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #fff;
  box-shadow:
    0 0 10px #fff,
    0 0 22px $agent-detection;
  transform: translate(-50%, -50%);
}
.holo-login__panel {
  position: relative;
  padding: 28px;
  overflow: hidden;
  border: 1px solid color-mix(in srgb, $agent-detection 60%, $border-color);
  border-radius: 18px;
  color: $text-primary;
  background: linear-gradient(
    145deg,
    color-mix(in srgb, $agent-detection 13%, $surface-color),
    color-mix(in srgb, $agent-detection 4%, $surface-color)
  );
  box-shadow:
    0 0 0 1px rgba(255, 255, 255, 0.4) inset,
    0 20px 54px color-mix(in srgb, $agent-detection 15%, transparent);
  backdrop-filter: blur(22px) saturate(140%);
}
.holo-login__grid {
  position: absolute;
  inset: 0;
  z-index: 0;
  opacity: 0.5;
  background-image:
    linear-gradient(color-mix(in srgb, $agent-detection 14%, transparent) 1px, transparent 1px),
    linear-gradient(
      90deg,
      color-mix(in srgb, $agent-detection 14%, transparent) 1px,
      transparent 1px
    );
  background-size: 26px 26px;
  mask-image: radial-gradient(circle at 50% 0%, black, transparent 75%);
}
.holo-login__panel > :not(.holo-login__grid) {
  position: relative;
  z-index: 1;
}
.holo-login__kicker {
  color: $agent-detection;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.16em;
}
.holo-login__brand {
  margin: 8px 0 2px;
  font-size: 30px;
  font-weight: 700;
  letter-spacing: -0.03em;
}
h2 {
  margin: 0 0 6px;
  color: $text-secondary;
  font-size: 16px;
  font-weight: 600;
  letter-spacing: -0.01em;
}
p {
  margin: 0 0 20px;
  color: $text-secondary;
  font-size: 13px;
  line-height: 1.6;
}
.holo-login__submit {
  width: 100%;
  margin-top: 4px;
}
.holo-login :deep(.el-input__wrapper) {
  background: color-mix(in srgb, $surface-color 82%, transparent);
}
.holo-login__footer {
  margin: 16px 0 0;
  text-align: center;
  font-size: 13px;
}
.holo-login__footer a {
  margin-left: 4px;
  color: $agent-detection;
  font-weight: 600;
}
.holo-login__footer a:hover {
  text-decoration: underline;
}
@media (max-width: 760px) {
  .holo-login {
    padding-top: 128px;
  }
  .holo-login__beam {
    top: -96px;
    height: 224px;
  }
}
@media (prefers-reduced-motion: reduce) {
  .holo-login__beam {
    opacity: 1;
    transform: translateX(-50%);
  }
}
</style>
