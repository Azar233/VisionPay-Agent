import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'

/**
 * 登录表单逻辑。认证仍由 frontend 原有的 user store 负责，
 * 此处只允许不同的登录界面复用同一套提交行为。
 */
export function useLoginForm({ onSuccess } = {}) {
  const router = useRouter()
  const route = useRoute()
  const userStore = useUserStore()
  const formRef = ref(null)
  const loading = ref(false)
  const loginForm = reactive({ username: '', password: '' })
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

  async function handleLogin() {
    const valid = await formRef.value.validate().catch(() => false)
    if (!valid) return false

    loading.value = true
    try {
      const result = await userStore.login({
        username: loginForm.username,
        password: loginForm.password,
      })
      ElMessage.success('登录成功')
      const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
      if (onSuccess) await onSuccess({ result, redirect })
      else await router.push(redirect)
      return true
    } catch {
      // 错误已在 frontend 原有的 Axios 拦截器中统一处理。
      return false
    } finally {
      loading.value = false
    }
  }

  return { formRef, loading, loginForm, loginRules, handleLogin }
}
