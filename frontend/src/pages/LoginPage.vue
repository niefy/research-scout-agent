<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showToast } from 'vant'

import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const mode = ref<'login' | 'register'>('login')
const submitting = ref(false)
const form = reactive({
  email: '',
  password: '',
  nickname: '',
})

function switchMode(next: 'login' | 'register'): void {
  mode.value = next
}

async function submit(): Promise<void> {
  if (!form.email.trim() || !form.password) {
    showToast('请填写邮箱和密码')
    return
  }
  if (mode.value === 'register' && !form.nickname.trim()) {
    showToast('请填写昵称')
    return
  }
  if (form.password.length < 8) {
    showToast('密码至少 8 位')
    return
  }

  submitting.value = true
  try {
    if (mode.value === 'login') {
      await auth.login(form.email.trim(), form.password)
    } else {
      await auth.register(form.email.trim(), form.password, form.nickname.trim())
    }
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/feed'
    await router.replace(redirect)
  } catch (error) {
    showToast(error instanceof Error ? error.message : '操作失败，请重试')
  } finally {
    submitting.value = false
  }
}

function fillDemo(): void {
  mode.value = 'login'
  form.email = 'demo@example.com'
  form.password = 'demo12345'
}
</script>

<template>
  <div class="login-page">
    <div class="login-page__glow login-page__glow--one" />
    <div class="login-page__glow login-page__glow--two" />

    <header class="login-brand">
      <div class="login-brand__mark">R</div>
      <div>
        <p class="login-brand__eyebrow">RESEARCH SCOUT</p>
        <h1 class="login-brand__title">研报雷达</h1>
      </div>
    </header>

    <p class="login-tagline">把财经研报、论坛帖子和新闻，变成可解释、可个性化的研究信号。</p>

    <section class="login-card">
      <div class="login-switch">
        <button
          type="button"
          :class="{ active: mode === 'login' }"
          @click="switchMode('login')"
        >
          登录
        </button>
        <button
          type="button"
          :class="{ active: mode === 'register' }"
          @click="switchMode('register')"
        >
          注册
        </button>
      </div>

      <label class="login-field">
        <span>邮箱</span>
        <input
          v-model="form.email"
          type="email"
          inputmode="email"
          autocomplete="email"
          placeholder="you@example.com"
        />
      </label>

      <label v-if="mode === 'register'" class="login-field">
        <span>昵称</span>
        <input
          v-model="form.nickname"
          type="text"
          maxlength="64"
          autocomplete="nickname"
          placeholder="怎么称呼你"
        />
      </label>

      <label class="login-field">
        <span>密码</span>
        <input
          v-model="form.password"
          type="password"
          :autocomplete="mode === 'login' ? 'current-password' : 'new-password'"
          placeholder="至少 8 位"
          @keyup.enter="submit"
        />
      </label>

      <van-button
        block
        round
        type="primary"
        :loading="submitting"
        loading-text="请稍候"
        class="login-submit"
        @click="submit"
      >
        {{ mode === 'login' ? '进入雷达' : '创建账号' }}
      </van-button>

      <button v-if="mode === 'login'" type="button" class="login-demo" @click="fillDemo">
        使用演示账号 · demo@example.com
      </button>
    </section>

    <footer class="login-footer">
      <p>内容由 AI 分析生成，仅供研究参考，不构成投资建议。</p>
    </footer>
  </div>
</template>

<style scoped>
.login-page {
  position: relative;
  min-height: 100vh;
  padding: 56px 22px 32px;
  overflow: hidden;
  background:
    radial-gradient(900px 420px at 110% -10%, rgba(194, 65, 12, 0.4), transparent 62%),
    radial-gradient(700px 380px at -30% 110%, rgba(45, 112, 169, 0.4), transparent 60%),
    linear-gradient(150deg, #081827 0%, #0e2439 45%, #14344f 100%);
  color: #fff;
}

.login-page__glow {
  position: absolute;
  border-radius: 50%;
  filter: blur(70px);
  opacity: 0.5;
  pointer-events: none;
}

.login-page__glow--one {
  width: 220px;
  height: 220px;
  top: 18%;
  right: -90px;
  background: rgba(194, 65, 12, 0.55);
}

.login-page__glow--two {
  width: 260px;
  height: 260px;
  bottom: -120px;
  left: -80px;
  background: rgba(56, 128, 190, 0.45);
}

.login-brand {
  position: relative;
  display: flex;
  align-items: center;
  gap: 14px;
}

.login-brand__mark {
  display: grid;
  place-items: center;
  width: 48px;
  height: 48px;
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.22);
  background: linear-gradient(145deg, rgba(255, 255, 255, 0.16), rgba(255, 255, 255, 0.04));
  font-size: 24px;
  font-weight: 800;
  letter-spacing: -0.04em;
  color: #fff;
}

.login-brand__eyebrow {
  margin: 0;
  font-size: 10px;
  letter-spacing: 0.3em;
  color: rgba(255, 255, 255, 0.5);
}

.login-brand__title {
  margin: 3px 0 0;
  font-size: 24px;
  font-weight: 700;
  letter-spacing: 0.06em;
}

.login-tagline {
  position: relative;
  max-width: 320px;
  margin: 28px 0 26px;
  font-size: 13px;
  line-height: 1.8;
  color: rgba(255, 255, 255, 0.66);
}

.login-card {
  position: relative;
  padding: 20px 18px 18px;
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 24px 60px rgba(3, 12, 22, 0.45);
  color: var(--rs-ink);
  backdrop-filter: blur(8px);
}

.login-switch {
  display: flex;
  gap: 6px;
  padding: 4px;
  margin-bottom: 20px;
  border-radius: 12px;
  background: var(--rs-neutral-soft);
}

.login-switch button {
  flex: 1;
  padding: 9px 0;
  border: none;
  border-radius: 9px;
  background: transparent;
  font-size: 13px;
  font-weight: 600;
  color: var(--rs-muted);
  cursor: pointer;
  transition: all 0.2s ease;
}

.login-switch button.active {
  background: #fff;
  color: var(--rs-ink);
  box-shadow: 0 2px 8px rgba(16, 35, 58, 0.1);
}

.login-field {
  display: block;
  margin-bottom: 14px;
}

.login-field span {
  display: block;
  margin-bottom: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--rs-ink-soft);
}

.login-field input {
  width: 100%;
  padding: 12px 14px;
  border: 1px solid var(--rs-line);
  border-radius: 12px;
  background: #fbfcfe;
  font-size: 14px;
  color: var(--rs-ink);
  outline: none;
  transition: border-color 0.2s ease;
}

.login-field input::placeholder {
  color: #a9b5c4;
}

.login-field input:focus {
  border-color: var(--rs-accent);
  background: #fff;
}

.login-submit {
  margin-top: 8px;
  height: 46px;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.04em;
}

.login-demo {
  display: block;
  width: 100%;
  margin-top: 14px;
  padding: 6px 0;
  border: none;
  background: transparent;
  font-size: 11.5px;
  color: var(--rs-muted);
  cursor: pointer;
}

.login-demo:hover {
  color: var(--rs-accent);
}

.login-footer {
  position: relative;
  margin-top: 26px;
  text-align: center;
}

.login-footer p {
  margin: 0;
  font-size: 10.5px;
  line-height: 1.7;
  color: rgba(255, 255, 255, 0.36);
}
</style>
