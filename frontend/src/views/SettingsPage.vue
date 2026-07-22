<template>
  <div class="settings-page">
    <header class="page-header">
      <div>
        <span class="vp-kicker">Account</span>
        <h1 class="vp-page-title">账号设置</h1>
        <p class="vp-page-subtitle">
          维护个人资料、Agent 响应偏好与登录安全。用户名用于登录，昵称用于界面展示。
        </p>
      </div>
    </header>

    <section class="settings-workspace">
      <aside class="settings-sidebar" aria-label="设置分类">
        <div class="sidebar-heading">
          <strong>设置中心</strong>
          <span>管理账户、Agent 与桌宠偏好</span>
        </div>

        <nav class="settings-nav" role="tablist" aria-label="设置分类">
          <button
            type="button"
            class="settings-nav-item profile"
            :class="{ active: activeSettingsSection === 'profile' }"
            role="tab"
            :aria-selected="activeSettingsSection === 'profile'"
            aria-controls="settings-profile-panel"
            @click="activeSettingsSection = 'profile'"
          >
            <span class="nav-icon"
              ><el-icon><User /></el-icon
            ></span>
            <span class="nav-copy"><strong>个人资料</strong><small>头像与联系方式</small></span>
          </button>
          <button
            type="button"
            class="settings-nav-item instructions"
            :class="{ active: activeSettingsSection === 'instructions' }"
            role="tab"
            :aria-selected="activeSettingsSection === 'instructions'"
            aria-controls="settings-instructions-panel"
            @click="activeSettingsSection = 'instructions'"
          >
            <span class="nav-icon"
              ><el-icon><EditPen /></el-icon
            ></span>
            <span class="nav-copy"><strong>自定义指令</strong><small>语言、语气与格式</small></span>
          </button>
          <button
            type="button"
            class="settings-nav-item security"
            :class="{ active: activeSettingsSection === 'security' }"
            role="tab"
            :aria-selected="activeSettingsSection === 'security'"
            aria-controls="settings-security-panel"
            @click="activeSettingsSection = 'security'"
          >
            <span class="nav-icon"
              ><el-icon><Lock /></el-icon
            ></span>
            <span class="nav-copy"><strong>账号安全</strong><small>修改登录密码</small></span>
          </button>
          <button
            type="button"
            class="settings-nav-item pet"
            :class="{ active: activeSettingsSection === 'pet' }"
            role="tab"
            :aria-selected="activeSettingsSection === 'pet'"
            aria-controls="settings-pet-panel"
            @click="activeSettingsSection = 'pet'"
          >
            <span class="nav-icon"
              ><el-icon><Monitor /></el-icon
            ></span>
            <span class="nav-copy"><strong>桌宠设置</strong><small>显示与尺寸偏好</small></span>
          </button>
        </nav>
      </aside>

      <div class="settings-content">
        <section
          v-show="activeSettingsSection === 'profile'"
          id="settings-profile-panel"
          class="settings-panel"
          role="tabpanel"
        >
          <header class="panel-heading">
            <div class="panel-icon profile">
              <el-icon><User /></el-icon>
            </div>
            <div>
              <h2>个人资料</h2>
              <p>管理头像、展示昵称和联系方式，登录用户名不可在此修改。</p>
            </div>
          </header>

          <div class="panel-body profile-body">
            <el-form
              ref="profileFormRef"
              :model="profileForm"
              :rules="profileRules"
              label-position="top"
            >
              <div class="avatar-editor">
                <el-avatar :size="64" :src="profileForm.avatar || undefined" class="profile-avatar">
                  {{ avatarInitial }}
                </el-avatar>
                <div class="avatar-meta">
                  <strong>自定义头像</strong>
                  <span>支持 JPG、PNG、WEBP、BMP，文件不超过 2MB。</span>
                  <div class="avatar-actions">
                    <el-upload
                      :auto-upload="false"
                      :show-file-list="false"
                      accept="image/jpeg,image/png,image/webp,image/bmp"
                      :on-change="handleAvatarSelect"
                    >
                      <el-button :icon="Upload" :loading="avatarLoading">上传头像</el-button>
                    </el-upload>
                    <el-button
                      v-if="profileForm.avatar"
                      text
                      :disabled="avatarLoading"
                      @click="resetAvatar"
                      >恢复默认</el-button
                    >
                  </div>
                </div>
              </div>
              <div class="form-grid">
                <el-form-item label="用户名"
                  ><el-input v-model="profileForm.username" disabled
                /></el-form-item>
                <el-form-item label="昵称" prop="nickname"
                  ><el-input
                    v-model.trim="profileForm.nickname"
                    placeholder="未设置时显示用户名"
                    maxlength="50"
                    clearable
                /></el-form-item>
                <el-form-item label="邮箱" prop="email"
                  ><el-input v-model.trim="profileForm.email" placeholder="name@example.com"
                /></el-form-item>
                <el-form-item label="手机号" prop="phone"
                  ><el-input v-model.trim="profileForm.phone" placeholder="选填" maxlength="20"
                /></el-form-item>
                <el-form-item label="注册时间"
                  ><el-input :model-value="formatDate(profileForm.created_at)" disabled
                /></el-form-item>
              </div>
              <div class="form-actions">
                <el-button type="primary" :loading="profileLoading" @click="saveProfile"
                  >保存个人资料</el-button
                >
              </div>
            </el-form>
          </div>
        </section>

        <section
          v-show="activeSettingsSection === 'instructions'"
          id="settings-instructions-panel"
          class="settings-panel"
          role="tabpanel"
        >
          <header class="panel-heading instructions-heading">
            <div class="panel-icon instructions">
              <el-icon><EditPen /></el-icon>
            </div>
            <div>
              <h2>Agent 自定义指令</h2>
              <p>为当前账号的所有管理端 Agent 提供统一的响应偏好。</p>
            </div>
            <el-button
              type="primary"
              :loading="instructionsLoading"
              :disabled="!instructionsDirty"
              @click="saveAgentInstructions"
            >
              保存
            </el-button>
          </header>

          <div class="instructions-editor">
            <div class="instructions-copy">
              <strong>希望 Agent 如何回答</strong>
              <p>
                可以指定语言、角色化口吻、自称方式、详细程度和内容格式。保存后，新消息会立即使用这些偏好。
              </p>
            </div>
            <el-input
              v-model="agentInstructions"
              type="textarea"
              :autosize="{ minRows: 10, maxRows: 18 }"
              maxlength="4000"
              show-word-limit
              resize="vertical"
              placeholder="例如：始终使用中文，语气专业直接；先给结论，再给必要说明；涉及多项数据时优先使用 Markdown 表格。"
              aria-label="Agent 自定义指令"
            />
            <div class="instruction-examples">
              <span>快速添加</span>
              <button
                v-for="example in instructionExamples"
                :key="example"
                type="button"
                @click="appendInstruction(example)"
              >
                {{ example }}
              </button>
            </div>
            <div class="instructions-boundary">
              <div>
                <strong>应用边界</strong>
                <span
                  >可以改变表达角色和口吻，但不会改变 Agent
                  的真实身份、职责、工具权限、事实来源、操作确认和审计规则。</span
                >
              </div>
              <el-button
                text
                :disabled="instructionsLoading || !agentInstructions"
                @click="clearAgentInstructions"
                >清除指令</el-button
              >
            </div>
          </div>
        </section>

        <section
          v-show="activeSettingsSection === 'security'"
          id="settings-security-panel"
          class="settings-panel"
          role="tabpanel"
        >
          <header class="panel-heading">
            <div class="panel-icon security">
              <el-icon><Lock /></el-icon>
            </div>
            <div>
              <h2>账号安全</h2>
              <p>定期更新登录密码，降低账号凭据泄露风险。</p>
            </div>
          </header>

          <div class="security-layout">
            <div class="security-form-panel">
              <el-alert
                title="新密码将在下次登录时生效，当前登录不会退出。"
                type="info"
                :closable="false"
                show-icon
              />
              <el-form
                ref="passwordFormRef"
                :model="passwordForm"
                :rules="passwordRules"
                label-position="top"
                class="password-form"
              >
                <el-form-item label="当前密码" prop="old_password"
                  ><el-input
                    v-model="passwordForm.old_password"
                    type="password"
                    show-password
                    autocomplete="current-password"
                /></el-form-item>
                <el-form-item label="新密码" prop="new_password"
                  ><el-input
                    v-model="passwordForm.new_password"
                    type="password"
                    show-password
                    autocomplete="new-password"
                /></el-form-item>
                <el-form-item label="确认新密码" prop="confirm_password"
                  ><el-input
                    v-model="passwordForm.confirm_password"
                    type="password"
                    show-password
                    autocomplete="new-password"
                /></el-form-item>
                <div class="form-actions">
                  <el-button type="primary" :loading="passwordLoading" @click="savePassword"
                    >更新登录密码</el-button
                  >
                </div>
              </el-form>
            </div>
            <aside class="security-note">
              <strong>密码建议</strong>
              <ul>
                <li>至少使用 6 个字符</li>
                <li>避免与当前密码重复</li>
                <li>不要复用其他平台的密码</li>
              </ul>
            </aside>
          </div>
        </section>

        <section
          v-show="activeSettingsSection === 'pet'"
          id="settings-pet-panel"
          class="settings-panel"
          role="tabpanel"
        >
          <header class="panel-heading">
            <div class="panel-icon pet">
              <el-icon><Monitor /></el-icon>
            </div>
            <div>
              <h2>桌宠设置</h2>
              <p>控制桌宠的显示状态和界面占用空间。</p>
            </div>
          </header>

          <div class="pet-settings-grid">
            <div class="pet-preview">
              <div class="pet-preview-canvas">
                <span class="pet-preview-sprite" :style="petPreviewStyle" />
              </div>
              <div>
                <strong>实时预览</strong
                ><span>{{ petVisible ? `当前尺寸 ${petSizePercent}%` : '宠物当前已隐藏' }}</span>
              </div>
            </div>

            <div class="pet-controls">
              <div class="preference-row">
                <div><strong>显示桌宠</strong><span>在登录和注册页之外显示宠物</span></div>
                <el-switch v-model="petVisible" aria-label="显示桌宠" />
              </div>

              <div class="size-preference">
                <div class="preference-heading">
                  <div><strong>宠物大小</strong><span>拖动滑杆会立即更新桌宠尺寸</span></div>
                  <em>{{ petSizePercent }}%</em>
                </div>
                <el-slider
                  v-model="petSizePercent"
                  :min="70"
                  :max="130"
                  :step="5"
                  :format-tooltip="formatPetSize"
                  show-stops
                />
                <div class="size-labels">
                  <span>紧凑 70%</span><span>默认 100%</span><span>放大 130%</span>
                </div>
              </div>

              <div class="preference-footer">
                <span>设置仅保存在当前浏览器中。</span>
                <el-button text @click="resetPetPreferences">恢复默认</el-button>
              </div>
            </div>
          </div>
        </section>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { EditPen, Lock, Monitor, Upload, User } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import petSprites from '@/assets/pet/visionpay-pet-sprites-v4.png'
import { getUserInfoApi } from '@/api/auth'
import {
  changePassword as changePasswordApi,
  getAgentInstructions as getAgentInstructionsApi,
  updateAgentInstructions as updateAgentInstructionsApi,
  updateProfile as updateProfileApi,
  uploadAvatar as uploadAvatarApi,
} from '@/api/user'
import { useUserStore } from '@/stores/user'
import { useVisionPetStore, VISION_PET_DEFAULT_SIZE } from '@/stores/visionPet'

const userStore = useUserStore()
const petStore = useVisionPetStore()
const profileFormRef = ref()
const passwordFormRef = ref()
const profileLoading = ref(false)
const passwordLoading = ref(false)
const avatarLoading = ref(false)
const instructionsLoading = ref(false)
const activeSettingsSection = ref('profile')
const agentInstructions = ref('')
const savedAgentInstructions = ref('')
const profileForm = reactive({
  username: '',
  nickname: '',
  email: '',
  phone: '',
  avatar: '',
  created_at: null,
})
const passwordForm = reactive({ old_password: '', new_password: '', confirm_password: '' })
const avatarInitial = computed(
  () => (profileForm.nickname || profileForm.username)?.charAt(0)?.toUpperCase() || 'U',
)
const instructionsDirty = computed(
  () => agentInstructions.value.trim() !== savedAgentInstructions.value,
)
const instructionExamples = [
  '始终使用中文回答',
  '语气专业、直接，不使用寒暄',
  '先给结论，再说明关键依据',
  '多项数据优先使用 Markdown 表格',
]
const petVisible = computed({
  get: () => petStore.visible,
  set: (visible) => petStore.setVisible(visible),
})
const petSizePercent = computed({
  get: () => petStore.sizePercent,
  set: (sizePercent) => petStore.setSizePercent(sizePercent),
})
const petPreviewStyle = computed(() => {
  const scale = petStore.sizePercent / 100
  return {
    width: `${50 * scale}px`,
    height: `${71 * scale}px`,
    backgroundImage: `url(${petSprites})`,
  }
})
const profileRules = {
  nickname: [{ max: 50, message: '昵称不能超过 50 个字符', trigger: ['blur', 'change'] }],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '邮箱格式不正确', trigger: ['blur', 'change'] },
  ],
  phone: [{ pattern: /^$|^[+\d][\d\s-]{5,19}$/, message: '手机号格式不正确', trigger: 'blur' }],
}
const passwordRules = {
  old_password: [{ required: true, message: '请输入当前密码', trigger: 'blur' }],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, max: 100, message: '密码长度为 6-100 个字符', trigger: 'blur' },
    {
      validator: (_rule, value, callback) =>
        value === passwordForm.old_password
          ? callback(new Error('新密码不能与当前密码相同'))
          : callback(),
      trigger: 'blur',
    },
  ],
  confirm_password: [
    { required: true, message: '请再次输入新密码', trigger: 'blur' },
    {
      validator: (_rule, value, callback) =>
        value !== passwordForm.new_password
          ? callback(new Error('两次输入的新密码不一致'))
          : callback(),
      trigger: ['blur', 'change'],
    },
  ],
}

function formatDate(value) {
  if (!value) return '—'
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(value))
}

function fillProfile(user) {
  Object.assign(profileForm, {
    username: user.username || '',
    nickname: user.nickname || '',
    email: user.email || '',
    phone: user.phone || '',
    avatar: user.avatar || '',
    created_at: user.created_at,
  })
}

function formatPetSize(value) {
  return `${value}%`
}

function resetPetPreferences() {
  petStore.resetPreferences()
  ElMessage.success(`桌宠设置已恢复为默认尺寸 ${VISION_PET_DEFAULT_SIZE}%`)
}

async function loadProfile() {
  try {
    const user = await getUserInfoApi()
    fillProfile(user)
    userStore.setUser(user)
  } catch {
    ElMessage.error('个人资料加载失败')
  }
}

async function loadAgentInstructions() {
  instructionsLoading.value = true
  try {
    const data = await getAgentInstructionsApi()
    agentInstructions.value = data.instructions || ''
    savedAgentInstructions.value = agentInstructions.value
  } catch {
    ElMessage.error('自定义指令加载失败')
  } finally {
    instructionsLoading.value = false
  }
}

function appendInstruction(value) {
  if (agentInstructions.value.includes(value)) return
  agentInstructions.value = [agentInstructions.value.trim(), value].filter(Boolean).join('\n')
}

async function saveAgentInstructions() {
  instructionsLoading.value = true
  try {
    const data = await updateAgentInstructionsApi(agentInstructions.value)
    agentInstructions.value = data.instructions || ''
    savedAgentInstructions.value = agentInstructions.value
    ElMessage.success(data.message || '自定义指令已保存')
  } finally {
    instructionsLoading.value = false
  }
}

async function clearAgentInstructions() {
  agentInstructions.value = ''
  await saveAgentInstructions()
}

async function saveProfile() {
  if (!(await profileFormRef.value.validate().catch(() => false))) return
  profileLoading.value = true
  try {
    const data = await updateProfileApi({
      nickname: profileForm.nickname,
      email: profileForm.email,
      phone: profileForm.phone,
    })
    fillProfile({ ...profileForm, ...data.user })
    userStore.setUser({ ...userStore.user, ...data.user })
    ElMessage.success('个人资料已更新')
  } finally {
    profileLoading.value = false
  }
}

async function handleAvatarSelect(uploadFile) {
  const file = uploadFile.raw
  if (!file) return
  const allowedTypes = ['image/jpeg', 'image/png', 'image/webp', 'image/bmp']
  if (!allowedTypes.includes(file.type)) {
    ElMessage.warning('仅支持 JPG、PNG、WEBP、BMP 图片')
    return
  }
  if (file.size > 2 * 1024 * 1024) {
    ElMessage.warning('头像文件不能超过 2MB')
    return
  }
  const formData = new FormData()
  formData.append('file', file)
  avatarLoading.value = true
  try {
    const data = await uploadAvatarApi(formData)
    fillProfile({ ...profileForm, ...data.user })
    userStore.setUser({ ...userStore.user, ...data.user })
    ElMessage.success('头像已更新')
  } finally {
    avatarLoading.value = false
  }
}

async function resetAvatar() {
  avatarLoading.value = true
  try {
    const data = await updateProfileApi({ avatar: '' })
    fillProfile({ ...profileForm, ...data.user })
    userStore.setUser({ ...userStore.user, ...data.user })
    ElMessage.success('已恢复默认头像')
  } finally {
    avatarLoading.value = false
  }
}

async function savePassword() {
  if (!(await passwordFormRef.value.validate().catch(() => false))) return
  passwordLoading.value = true
  try {
    await changePasswordApi({
      old_password: passwordForm.old_password,
      new_password: passwordForm.new_password,
    })
    Object.assign(passwordForm, { old_password: '', new_password: '', confirm_password: '' })
    passwordFormRef.value.clearValidate()
    ElMessage.success('密码修改成功')
  } finally {
    passwordLoading.value = false
  }
}

onMounted(() => Promise.all([loadProfile(), loadAgentInstructions()]))
</script>

<style lang="scss" scoped>
.settings-page {
  min-height: 100%;
  padding: 32px;
  display: flex;
  flex-direction: column;
  gap: 18px;
  color: $text-primary;
  background: $bg-color;
}

.page-header {
  padding: 8px 0 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;

  > div {
    width: 100%;
    min-width: 0;
  }

  h1 {
    margin: 10px 0 0;
    color: $text-primary;
    font-family: 'Space Grotesk', 'DM Sans', sans-serif;
    font-size: 40px;
    line-height: 1.08;
    letter-spacing: 0;
  }

  p {
    max-width: none;
    margin: 12px 0 0;
    color: $text-secondary;
    font-size: 16px;
    line-height: 1.6;
    white-space: nowrap;
  }
}

.settings-workspace {
  min-height: 590px;
  display: grid;
  grid-template-columns: 236px minmax(0, 1fr);
  overflow: hidden;
  border: 1px solid $border-color;
  border-radius: $border-radius-lg;
  background: $surface-color;
  box-shadow: $shadow-sm;
}

.settings-sidebar {
  padding: 22px 14px;
  border-right: 1px solid $border-color;
  background: color-mix(in srgb, $surface-muted 78%, $surface-color);
}

.sidebar-heading {
  padding: 0 10px 18px;

  strong,
  span {
    display: block;
  }
  strong {
    color: $text-primary;
    font-size: 15px;
    font-weight: 650;
  }
  span {
    margin-top: 5px;
    color: $text-secondary;
    font-size: 11px;
    line-height: 1.5;
  }
}

.settings-nav {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.settings-nav-item {
  width: 100%;
  min-height: 64px;
  padding: 10px 12px;
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr);
  align-items: center;
  gap: 10px;
  border: 1px solid transparent;
  border-radius: 12px;
  color: $text-secondary;
  background: transparent;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition:
    color 0.18s ease,
    background-color 0.18s ease,
    border-color 0.18s ease,
    box-shadow 0.18s ease;

  &:hover {
    color: $text-primary;
    border-color: $border-color;
    background: $surface-color;
  }

  &:focus-visible {
    outline: 2px solid color-mix(in srgb, $primary-color 52%, transparent);
    outline-offset: 2px;
  }

  &.active {
    color: $text-primary;
    border-color: $border-color;
    background: $surface-color;
    box-shadow: $shadow-sm;
  }
}

.nav-icon {
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  border-radius: 10px;
  color: $text-secondary;
  background: $surface-muted;
  font-size: 17px;
  transition:
    color 0.18s ease,
    background-color 0.18s ease;
}

.settings-nav-item.profile.active .nav-icon {
  color: $primary-color;
  background: $primary-soft;
}
.settings-nav-item.security.active .nav-icon {
  color: #9b51c4;
  background: rgba(175, 82, 222, 0.12);
}
.settings-nav-item.instructions.active .nav-icon {
  color: #c56a16;
  background: rgba(245, 158, 11, 0.13);
}
.settings-nav-item.pet.active .nav-icon {
  color: #0d9f73;
  background: rgba(16, 185, 129, 0.12);
}

.nav-copy {
  min-width: 0;

  strong,
  small {
    display: block;
  }
  strong {
    font-size: 14px;
    font-weight: 600;
  }
  small {
    margin-top: 4px;
    color: $text-secondary;
    font-size: 10px;
    line-height: 1.4;
  }
}

.settings-content {
  min-width: 0;
  padding: 30px 32px 34px;
}

.settings-panel {
  width: 100%;
  max-width: 1120px;
}

.panel-heading {
  margin-bottom: 24px;
  padding-bottom: 20px;
  display: flex;
  align-items: center;
  gap: 13px;
  border-bottom: 1px solid $border-color;

  h2 {
    margin: 0;
    color: $text-primary;
    font-size: 22px;
    font-weight: 650;
    letter-spacing: -0.01em;
  }
  p {
    margin: 5px 0 0;
    color: $text-secondary;
    font-size: 12px;
    line-height: 1.5;
  }
}

.panel-icon {
  width: 42px;
  height: 42px;
  display: grid;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 12px;
  font-size: 19px;

  &.profile {
    color: $primary-color;
    background: $primary-soft;
  }
  &.security {
    color: #9b51c4;
    background: rgba(175, 82, 222, 0.12);
  }
  &.instructions {
    color: #c56a16;
    background: rgba(245, 158, 11, 0.13);
  }
  &.pet {
    color: #0d9f73;
    background: rgba(16, 185, 129, 0.12);
  }
}

.instructions-heading {
  align-items: center;

  > div:nth-child(2) {
    min-width: 0;
  }
  > .el-button {
    margin-left: auto;
    min-width: 78px;
  }
}

.instructions-editor {
  max-width: 900px;
  padding: 22px;
  border: 1px solid $border-color;
  border-radius: 16px;
  background: color-mix(in srgb, $surface-muted 68%, $surface-color);
}

.instructions-copy {
  margin-bottom: 16px;

  strong {
    color: $text-primary;
    font-size: 15px;
  }
  p {
    margin: 6px 0 0;
    color: $text-secondary;
    font-size: 11px;
    line-height: 1.6;
  }
}

.instructions-editor :deep(.el-textarea__inner) {
  min-height: 224px !important;
  padding: 16px 17px 30px;
  border: 1px solid $border-color;
  border-radius: 13px;
  color: $text-primary;
  background: $surface-color;
  box-shadow: none;
  font-family: inherit;
  font-size: 14px;
  line-height: 1.7;

  &:focus {
    border-color: $primary-color;
    box-shadow: 0 0 0 3px $primary-soft;
  }
}

.instruction-examples {
  margin-top: 14px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;

  > span {
    margin-right: 2px;
    color: $text-placeholder;
    font-size: 10px;
  }
  button {
    padding: 6px 9px;
    border: 1px solid $border-color;
    border-radius: 999px;
    color: $text-secondary;
    background: $surface-color;
    font: inherit;
    font-size: 10px;
    cursor: pointer;
  }
  button:hover {
    color: $primary-color;
    border-color: color-mix(in srgb, $primary-color 34%, $border-color);
  }
}

.instructions-boundary {
  min-height: 64px;
  margin-top: 18px;
  padding-top: 15px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  border-top: 1px solid $border-color;

  strong,
  span {
    display: block;
  }
  strong {
    color: $text-primary;
    font-size: 11px;
  }
  span {
    margin-top: 4px;
    color: $text-placeholder;
    font-size: 10px;
    line-height: 1.5;
  }
}

.panel-body {
  max-width: 920px;
}

.avatar-editor {
  margin-bottom: 22px;
  padding: 18px;
  display: flex;
  align-items: center;
  gap: 16px;
  border: 1px solid $border-color;
  border-radius: 14px;
  background: $surface-muted;
}

.profile-avatar {
  flex: 0 0 auto;
  color: #fff;
  background: linear-gradient(145deg, $primary-color, $primary-hover);
  font-size: 25px;
  font-weight: 700;
  box-shadow: 0 10px 28px rgba(0, 113, 227, 0.2);
}

.avatar-meta {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;

  strong {
    color: $text-primary;
    font-size: 14px;
  }
  > span {
    color: $text-secondary;
    font-size: 11px;
    line-height: 1.5;
  }
}

.avatar-actions {
  margin-top: 3px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  column-gap: 20px;
}

.form-actions {
  padding-top: 2px;
  display: flex;
  justify-content: flex-end;
}

.security-layout {
  display: grid;
  grid-template-columns: minmax(0, 560px) minmax(240px, 300px);
  align-items: start;
  gap: 28px;
}

.security-form-panel .el-alert {
  margin-bottom: 20px;
}
.password-form :deep(.el-form-item) {
  margin-bottom: 18px;
}

.security-note {
  padding: 20px;
  border: 1px solid $border-color;
  border-radius: 14px;
  color: $text-secondary;
  background: $surface-muted;

  strong {
    color: $text-primary;
    font-size: 14px;
  }
  ul {
    margin: 14px 0 0;
    padding-left: 18px;
  }
  li {
    margin-top: 9px;
    font-size: 12px;
    line-height: 1.55;
  }
  li::marker {
    color: $primary-color;
  }
}

.pet-settings-grid {
  display: grid;
  grid-template-columns: 280px minmax(0, 560px);
  align-items: start;
  gap: 28px;
}

.pet-preview {
  min-height: 250px;
  padding: 24px;
  display: grid;
  align-content: center;
  justify-items: center;
  gap: 12px;
  border: 1px solid $border-color;
  border-radius: 14px;
  background: linear-gradient(145deg, $surface-muted, $primary-soft);
  text-align: center;

  strong,
  span {
    display: block;
  }
  strong {
    color: $text-primary;
    font-size: 15px;
  }
  span {
    margin-top: 5px;
    color: $text-secondary;
    font-size: 11px;
    line-height: 1.5;
  }
}

.pet-preview-canvas {
  width: 140px;
  height: 132px;
  display: grid;
  place-items: center;
}

.pet-preview-sprite {
  display: block;
  background-repeat: no-repeat;
  background-position: 0 0;
  background-size: 400% 200%;
  image-rendering: pixelated;
  image-rendering: crisp-edges;
  transition:
    width 0.2s ease,
    height 0.2s ease;
}

.pet-controls {
  padding: 0 20px;
  border: 1px solid $border-color;
  border-radius: 14px;
  background: $surface-color;
}

.preference-row {
  min-height: 86px;
  padding: 20px 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  border-bottom: 1px solid $border-color;

  strong,
  span {
    display: block;
  }
  strong {
    color: $text-primary;
    font-size: 14px;
  }
  span {
    margin-top: 4px;
    color: $text-secondary;
    font-size: 11px;
    line-height: 1.5;
  }
}

.size-preference {
  padding: 20px 0 18px;
}
.preference-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}
.preference-heading strong,
.preference-heading span {
  display: block;
}
.preference-heading strong {
  color: $text-primary;
  font-size: 14px;
}
.preference-heading span {
  margin-top: 4px;
  color: $text-secondary;
  font-size: 11px;
}
.preference-heading em {
  color: $primary-color;
  font-size: 13px;
  font-style: normal;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.size-preference :deep(.el-slider) {
  margin: 15px 4px 5px;
  width: calc(100% - 8px);
}
.size-labels {
  display: flex;
  justify-content: space-between;
  color: $text-placeholder;
  font-size: 9px;
}

.preference-footer {
  min-height: 58px;
  padding: 10px 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-top: 1px solid $border-color;

  > span {
    color: $text-placeholder;
    font-size: 10px;
  }
}

@media (max-width: 1040px) {
  .settings-workspace {
    grid-template-columns: 1fr;
  }

  .settings-sidebar {
    padding: 14px;
    overflow: hidden;
    border-right: 0;
    border-bottom: 1px solid $border-color;
  }

  .sidebar-heading {
    display: none;
  }

  .settings-nav {
    flex-direction: row;
    overflow-x: auto;
    scrollbar-width: thin;
  }

  .settings-nav-item {
    min-width: 190px;
    min-height: 58px;
  }
}

@media (max-width: 760px) {
  .settings-page {
    padding: 20px;
  }
  .page-header {
    align-items: flex-start;
    flex-direction: column;
  }
  .page-header h1 {
    font-size: 30px;
  }
  .page-header p {
    white-space: normal;
  }
  .settings-content {
    padding: 24px;
  }
  .security-layout,
  .pet-settings-grid {
    grid-template-columns: 1fr;
  }
  .pet-preview {
    min-height: 210px;
  }
}

@media (max-width: 620px) {
  .settings-page {
    padding: 16px;
  }
  .settings-workspace {
    min-height: 0;
    border-radius: 14px;
  }
  .settings-sidebar {
    padding: 10px;
  }
  .settings-nav-item {
    min-width: 162px;
    padding: 9px 10px;
  }
  .settings-content {
    padding: 20px 18px 24px;
  }
  .panel-heading {
    align-items: flex-start;
  }
  .instructions-heading {
    flex-wrap: wrap;
  }
  .instructions-heading > .el-button {
    margin-left: 55px;
  }
  .panel-heading h2 {
    font-size: 20px;
  }
  .avatar-editor {
    align-items: flex-start;
    flex-direction: column;
  }
  .form-grid {
    grid-template-columns: 1fr;
  }
  .pet-controls {
    padding: 0 16px;
  }
  .preference-footer {
    align-items: flex-start;
    flex-direction: column;
  }
  .instructions-editor {
    padding: 16px;
  }
  .instructions-boundary {
    align-items: flex-start;
    flex-direction: column;
  }
}

.settings-page {
  min-height: 100%;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
}
.settings-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.25fr) minmax(340px, 0.75fr);
  gap: 16px;
  align-items: start;
}
.settings-card {
  padding: 26px;
  background: $surface-color;
  border: 1px solid $border-color;
  border-radius: $border-radius-md;
  box-shadow: $shadow-sm;
}
.settings-card > header {
  margin-bottom: 24px;
  display: flex;
  align-items: center;
  gap: 13px;
}
.settings-card h2 {
  margin: 0;
  color: $text-primary;
  font-size: 19px;
  font-weight: 600;
}
.settings-card header p {
  margin: 4px 0 0;
  color: $text-secondary;
  font-size: 12px;
}
.card-icon {
  width: 42px;
  height: 42px;
  display: grid;
  place-items: center;
  border-radius: 13px;
  color: $primary-color;
  background: $primary-soft;
  font-size: 19px;
}
.card-icon.security {
  color: $secondary-color;
  background: color-mix(in srgb, $secondary-color 12%, transparent);
}
.avatar-editor {
  margin-bottom: 22px;
  padding: 16px;
  display: flex;
  align-items: center;
  gap: 16px;
  border: 1px solid $border-color;
  border-radius: $border-radius-md;
  background: $surface-muted;
}
.profile-avatar {
  flex: 0 0 auto;
  color: #fff;
  background: linear-gradient(145deg, $primary-color, $primary-hover);
  font-size: 28px;
  font-weight: 700;
  box-shadow: 0 10px 28px color-mix(in srgb, $primary-color 20%, transparent);
}
.avatar-meta {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.avatar-meta strong {
  color: $text-primary;
  font-size: 15px;
}
.avatar-meta span {
  color: $text-secondary;
  font-size: 12px;
}
.avatar-actions {
  margin-top: 4px;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.form-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  column-gap: 16px;
}
.form-actions {
  padding-top: 4px;
  display: flex;
  justify-content: flex-end;
}
.password-card .el-alert {
  margin-bottom: 20px;
}
@media (max-width: 1000px) {
  .settings-grid {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 700px) {
  .settings-page {
    padding: 16px;
  }
  .settings-card {
    padding: 24px;
  }
  .avatar-editor {
    align-items: flex-start;
    flex-direction: column;
  }
  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
