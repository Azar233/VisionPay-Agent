<template>
  <div class="customer-mode-control">
    <button type="button" class="customer-mode-exit-button" @click="openPasswordPad">
      <el-icon><Lock /></el-icon>
      <span>退出顾客模式</span>
    </button>

    <el-dialog
      v-model="dialogVisible"
      title="退出顾客模式"
      width="420px"
      class="customer-mode-password-dialog"
      append-to-body
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      align-center
      @closed="resetPassword"
    >
      <div class="password-dialog-copy">
        <strong>请输入六位退出密码</strong>
        <span>密码可在个人中心 · 账号安全中设置</span>
      </div>

      <div class="password-dots" aria-label="已输入的密码位数">
        <i v-for="index in 6" :key="index" :class="{ filled: password.length >= index }"></i>
      </div>
      <p v-if="passwordError" class="password-error" role="alert">{{ passwordError }}</p>

      <div class="touch-keypad" aria-label="数字密码键盘">
        <button v-for="digit in digits" :key="digit" type="button" @click="appendDigit(digit)">
          {{ digit }}
        </button>
        <button type="button" class="keypad-action" @click="clearPassword">清空</button>
        <button type="button" @click="appendDigit('0')">0</button>
        <button type="button" class="keypad-action" @click="removeDigit">退格</button>
      </div>

      <template #footer>
        <div class="password-dialog-actions">
          <el-button size="large" @click="dialogVisible = false">继续顾客模式</el-button>
          <el-button
            type="primary"
            size="large"
            :loading="verifying"
            :disabled="password.length !== 6"
            @click="verifyAndExit"
          >
            验证并退出
          </el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { Lock } from '@element-plus/icons-vue'
import { verifyCustomerModePassword } from '@/api/user'
import { useCustomerModeStore } from '@/stores/customerMode'
import { getBackendErrorMessage } from '@/utils/visionPet'

const customerModeStore = useCustomerModeStore()
const dialogVisible = ref(false)
const password = ref('')
const passwordError = ref('')
const verifying = ref(false)
const digits = ['1', '2', '3', '4', '5', '6', '7', '8', '9']

function resetPassword() {
  password.value = ''
  passwordError.value = ''
}

function openPasswordPad() {
  resetPassword()
  dialogVisible.value = true
}

function appendDigit(digit) {
  if (password.value.length >= 6) return
  password.value += digit
  passwordError.value = ''
}

function removeDigit() {
  password.value = password.value.slice(0, -1)
  passwordError.value = ''
}

function clearPassword() {
  password.value = ''
  passwordError.value = ''
}

async function verifyAndExit() {
  if (password.value.length !== 6 || verifying.value) return
  verifying.value = true
  passwordError.value = ''
  try {
    await verifyCustomerModePassword(password.value)
    customerModeStore.exit()
    dialogVisible.value = false
    if (document.fullscreenElement) await document.exitFullscreen().catch(() => {})
  } catch (error) {
    password.value = ''
    passwordError.value = getBackendErrorMessage(error, '退出密码不正确')
  } finally {
    verifying.value = false
  }
}
</script>

<style lang="scss" scoped>
.customer-mode-control {
  position: fixed;
  z-index: 2200;
  top: 18px;
  right: 18px;
}

.customer-mode-exit-button {
  min-height: 48px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 0 18px;
  border: 1px solid color-mix(in srgb, var(--vp-danger) 30%, var(--vp-border));
  border-radius: 999px;
  color: var(--vp-danger);
  background: color-mix(in srgb, var(--vp-surface) 94%, transparent);
  box-shadow: var(--vp-shadow-md);
  backdrop-filter: blur(14px);
  cursor: pointer;
  font-size: 14px;
  font-weight: 700;
}

.password-dialog-copy {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  color: var(--vp-text-secondary);

  strong {
    color: var(--vp-text);
    font-size: 18px;
  }

  span {
    font-size: 13px;
  }
}

.password-dots {
  display: flex;
  justify-content: center;
  gap: 14px;
  margin: 24px 0 14px;

  i {
    width: 16px;
    height: 16px;
    border: 2px solid var(--vp-border-strong);
    border-radius: 50%;
    background: transparent;
    transition:
      background 0.15s ease,
      border-color 0.15s ease;

    &.filled {
      border-color: var(--vp-primary);
      background: var(--vp-primary);
    }
  }
}

.password-error {
  min-height: 22px;
  margin: 0 0 8px;
  color: var(--vp-danger);
  text-align: center;
  font-size: 13px;
}

.touch-keypad {
  max-width: 320px;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  margin: 0 auto;

  button {
    min-height: 64px;
    border: 1px solid var(--vp-border);
    border-radius: 14px;
    color: var(--vp-text);
    background: var(--vp-surface-muted);
    cursor: pointer;
    font-size: 24px;
    font-weight: 700;
    touch-action: manipulation;

    &:active {
      color: #fff;
      background: var(--vp-primary);
      transform: scale(0.97);
    }
  }

  .keypad-action {
    color: var(--vp-text-secondary);
    font-size: 15px;
    font-weight: 600;
  }
}

.password-dialog-actions {
  display: flex;
  justify-content: stretch;
  gap: 12px;

  .el-button {
    min-height: 48px;
    flex: 1;
    margin: 0;
  }
}

@media (max-width: 520px) {
  .customer-mode-control {
    top: 10px;
    right: 10px;
  }

  .customer-mode-exit-button {
    min-height: 44px;
    padding: 0 14px;
  }
}
</style>
