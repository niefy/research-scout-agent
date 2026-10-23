import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { api } from '@/api/client'
import { clearTokens, getAccessToken, setTokens } from '@/api/tokens'
import type { Message, TokenPair, User } from '@/api/types'

const USER_KEY = 'rs_user'

function loadUser(): User | null {
  const raw = localStorage.getItem(USER_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as User
  } catch {
    return null
  }
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(loadUser())
  const loading = ref(false)
  const isAuthenticated = computed(() => Boolean(getAccessToken()))
  const isAdmin = computed(() => user.value?.role === 'admin')

  function persistUser(value: User | null): void {
    user.value = value
    if (value) localStorage.setItem(USER_KEY, JSON.stringify(value))
    else localStorage.removeItem(USER_KEY)
  }

  async function login(email: string, password: string): Promise<void> {
    loading.value = true
    try {
      const tokens = await api.post<TokenPair>('/auth/login', { email, password })
      setTokens(tokens.access_token, tokens.refresh_token)
      await fetchMe()
    } finally {
      loading.value = false
    }
  }

  async function register(email: string, password: string, nickname: string): Promise<void> {
    loading.value = true
    try {
      const tokens = await api.post<TokenPair>('/auth/register', {
        email,
        password,
        nickname,
      })
      setTokens(tokens.access_token, tokens.refresh_token)
      await fetchMe()
    } finally {
      loading.value = false
    }
  }

  async function fetchMe(): Promise<User> {
    const me = await api.get<User>('/users/me')
    persistUser(me)
    return me
  }

  async function updateProfile(payload: {
    nickname?: string
    scoring_config?: User['scoring_config']
    digest_email_enabled?: boolean
  }): Promise<User> {
    const me = await api.patch<User>('/users/me', payload)
    persistUser(me)
    return me
  }

  async function changePassword(oldPassword: string, newPassword: string): Promise<Message> {
    return api.post<Message>('/users/me/password', {
      old_password: oldPassword,
      new_password: newPassword,
    })
  }

  function logout(): void {
    clearTokens()
    user.value = null
  }

  return {
    user,
    loading,
    isAuthenticated,
    isAdmin,
    login,
    register,
    fetchMe,
    updateProfile,
    changePassword,
    logout,
  }
})
