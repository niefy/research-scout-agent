<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { showConfirmDialog, showToast } from 'vant'

import { useAuthStore } from '@/stores/auth'
import { formatDate } from '@/utils/format'

const router = useRouter()
const auth = useAuthStore()

const categoryMeta = [
  { key: 'stock', label: '个股', hint: '直接影响个股判断的研报' },
  { key: 'industry', label: '行业', hint: '产业链、供需与竞争格局' },
  { key: 'macro', label: '宏观', hint: '利率、政策与经济数据' },
] as const

const defaultWeights: Record<string, number> = { stock: 0.4, industry: 0.4, macro: 0.2 }
const defaultHalfLives: Record<string, number> = { stock: 7, industry: 14, macro: 30 }

const profilePopup = ref(false)
const nicknameDraft = ref('')
const profileSaving = ref(false)

const scoringPopup = ref(false)
const scoringSaving = ref(false)
const scoringForm = reactive({
  category_weights: { ...defaultWeights },
  half_life_days: { ...defaultHalfLives },
})

const passwordPopup = ref(false)
const passwordSaving = ref(false)
const passwordForm = reactive({
  old_password: '',
  new_password: '',
  confirm_password: '',
})

const user = computed(() => auth.user)
const initial = computed(() => (user.value?.nickname ?? '?').trim().slice(0, 1) || '?')

const effectiveWeights = computed<Record<string, number>>(() => ({
  ...defaultWeights,
  ...(user.value?.scoring_config?.category_weights ?? {}),
}))

function normalizedPercent(weights: Record<string, number>, key: string): string {
  const total = categoryMeta.reduce((sum, meta) => sum + (weights[meta.key] ?? 0), 0) || 1
  return `${Math.round(((weights[key] ?? 0) / total) * 100)}%`
}

function openProfile(): void {
  nicknameDraft.value = user.value?.nickname ?? ''
  profilePopup.value = true
}

async function saveProfile(): Promise<void> {
  if (!nicknameDraft.value.trim()) {
    showToast('昵称不能为空')
    return
  }
  profileSaving.value = true
  try {
    await auth.updateProfile({ nickname: nicknameDraft.value.trim() })
    profilePopup.value = false
    showToast('资料已更新')
  } catch (error) {
    showToast(error instanceof Error ? error.message : '保存失败')
  } finally {
    profileSaving.value = false
  }
}

function openScoring(): void {
  const config = user.value?.scoring_config ?? {}
  for (const meta of categoryMeta) {
    scoringForm.category_weights[meta.key] =
      config.category_weights?.[meta.key] ?? defaultWeights[meta.key]
    scoringForm.half_life_days[meta.key] =
      config.half_life_days?.[meta.key] ?? defaultHalfLives[meta.key]
  }
  scoringPopup.value = true
}

async function saveScoring(): Promise<void> {
  scoringSaving.value = true
  try {
    await auth.updateProfile({
      scoring_config: {
        category_weights: { ...scoringForm.category_weights },
        half_life_days: { ...scoringForm.half_life_days },
      },
    })
    scoringPopup.value = false
    showToast('评分偏好已保存')
  } catch (error) {
    showToast(error instanceof Error ? error.message : '保存失败')
  } finally {
    scoringSaving.value = false
  }
}

function openPassword(): void {
  passwordForm.old_password = ''
  passwordForm.new_password = ''
  passwordForm.confirm_password = ''
  passwordPopup.value = true
}

async function savePassword(): Promise<void> {
  if (!passwordForm.old_password || !passwordForm.new_password) {
    showToast('请填写完整')
    return
  }
  if (passwordForm.new_password.length < 8) {
    showToast('新密码至少 8 位')
    return
  }
  if (passwordForm.new_password !== passwordForm.confirm_password) {
    showToast('两次输入的新密码不一致')
    return
  }
  passwordSaving.value = true
  try {
    await auth.changePassword(passwordForm.old_password, passwordForm.new_password)
    passwordPopup.value = false
    showToast('密码已更新')
  } catch (error) {
    showToast(error instanceof Error ? error.message : '修改失败')
  } finally {
    passwordSaving.value = false
  }
}

async function logout(): Promise<void> {
  try {
    await showConfirmDialog({
      title: '退出登录',
      message: '退出后需要重新登录才能查看关注和自选。',
      confirmButtonText: '退出',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  auth.logout()
  await router.replace('/login')
}

onMounted(async () => {
  try {
    await auth.fetchMe()
  } catch {
    // token refresh handles expiration; keep cached profile on transient errors
  }
})
</script>

<template>
  <div class="page settings-page">
    <header class="hero settings-hero">
      <span class="hero__eyebrow">ACCOUNT</span>
      <h1 class="hero__title">我的</h1>
      <p class="hero__subtitle">作者权重、品类偏好与账户设置</p>
    </header>

    <section class="profile-card card">
      <div class="profile-card__avatar">{{ initial }}</div>
      <div class="profile-card__body">
        <div class="profile-card__name-row">
          <h2>{{ user?.nickname ?? '研究用户' }}</h2>
          <span class="chip chip--accent">{{ user?.role === 'admin' ? '管理员' : '用户' }}</span>
        </div>
        <p class="profile-card__email">{{ user?.email ?? user?.phone ?? '—' }}</p>
        <p class="profile-card__since">
          加入于 {{ user ? formatDate(user.created_at) : '—' }}
        </p>
      </div>
      <button type="button" class="profile-card__edit" @click="openProfile">
        编辑
      </button>
    </section>

    <section class="section">
      <div class="section__head">
        <h2 class="section__title">研究偏好</h2>
      </div>
      <div class="card settings-group">
        <button type="button" class="settings-row" @click="openScoring">
          <span class="settings-row__icon settings-row__icon--amber">
            <van-icon name="chart-trending-o" size="16" />
          </span>
          <span class="settings-row__body">
            <span class="settings-row__label">板块配额与半衰期</span>
            <span class="settings-row__value">
              个股 {{ normalizedPercent(effectiveWeights, 'stock') }} ·
              行业 {{ normalizedPercent(effectiveWeights, 'industry') }} ·
              宏观 {{ normalizedPercent(effectiveWeights, 'macro') }}
            </span>
          </span>
          <van-icon name="arrow" size="13" class="settings-row__arrow" />
        </button>

        <button type="button" class="settings-row" @click="router.push('/authors')">
          <span class="settings-row__icon settings-row__icon--blue">
            <van-icon name="friends-o" size="16" />
          </span>
          <span class="settings-row__body">
            <span class="settings-row__label">作者权重</span>
            <span class="settings-row__value">在「作者」页调整每位博主的关注权重</span>
          </span>
          <van-icon name="arrow" size="13" class="settings-row__arrow" />
        </button>

        <button type="button" class="settings-row" @click="router.push('/watchlist')">
          <span class="settings-row__icon settings-row__icon--green">
            <van-icon name="star-o" size="16" />
          </span>
          <span class="settings-row__body">
            <span class="settings-row__label">自选股</span>
            <span class="settings-row__value">查看个股、行业、宏观的综合评分</span>
          </span>
          <van-icon name="arrow" size="13" class="settings-row__arrow" />
        </button>
      </div>
    </section>

    <section class="section">
      <div class="section__head">
        <h2 class="section__title">账户安全</h2>
      </div>
      <div class="card settings-group">
        <button type="button" class="settings-row" @click="openPassword">
          <span class="settings-row__icon settings-row__icon--slate">
            <van-icon name="shield-o" size="16" />
          </span>
          <span class="settings-row__body">
            <span class="settings-row__label">修改密码</span>
            <span class="settings-row__value">至少 8 位，建议定期更换</span>
          </span>
          <van-icon name="arrow" size="13" class="settings-row__arrow" />
        </button>
      </div>
    </section>

    <section class="section">
      <div class="card about-card">
        <div class="about-card__head">
          <span class="about-card__mark">R</span>
          <div>
            <h3>研报雷达 · Research Scout</h3>
            <p>Phase 0 · MVP</p>
          </div>
        </div>
        <p class="about-card__text">
          内容每天从多个渠道采集，经 LLM 完成分类、评分与摘要；你的关注和权重只影响个人排序与自选聚合，不会改变全局分析结果。
        </p>
        <p class="about-card__disclaimer">
          所有内容与评分仅供研究参考，不构成任何投资建议。市场有风险，决策需独立判断。
        </p>
      </div>
    </section>

    <div class="settings-logout">
      <van-button block round plain type="danger" @click="logout">退出登录</van-button>
    </div>

    <!-- profile popup -->
    <van-popup v-model:show="profilePopup" position="bottom" round closeable>
      <div class="sheet">
        <h3 class="sheet__title">编辑资料</h3>
        <label class="sheet-label">
          昵称
          <input
            v-model="nicknameDraft"
            type="text"
            maxlength="64"
            class="sheet-input"
            placeholder="你的昵称"
          />
        </label>
        <p class="sheet-note">邮箱：{{ user?.email ?? '—' }}</p>
        <van-button
          block
          round
          type="primary"
          :loading="profileSaving"
          class="sheet__submit"
          @click="saveProfile"
        >
          保存
        </van-button>
      </div>
    </van-popup>

    <!-- scoring popup -->
    <van-popup v-model:show="scoringPopup" position="bottom" round closeable>
      <div class="sheet sheet--scroll">
        <h3 class="sheet__title">评分偏好</h3>
        <p class="sheet__subtitle">
          板块配额决定综合分中个股 / 行业 / 宏观的满分占比（默认 40 / 40 / 20，保存后按比例归一化）；
          半衰期决定文章权重随发布时间的衰减速度，越短衰减越快。
        </p>

        <div v-for="meta in categoryMeta" :key="meta.key" class="scoring-block">
          <div class="scoring-block__head">
            <span class="scoring-block__label">{{ meta.label }}</span>
            <span class="scoring-block__weight mono">
              {{ normalizedPercent(scoringForm.category_weights, meta.key) }}
            </span>
          </div>
          <van-slider
            v-model="scoringForm.category_weights[meta.key]"
            :min="0"
            :max="1"
            :step="0.05"
            bar-height="6px"
            active-color="#c2410c"
          />
          <div class="scoring-block__foot">
            <span class="scoring-block__hint">{{ meta.hint }}</span>
            <span class="scoring-block__half-life">
              半衰期
              <van-stepper
                v-model="scoringForm.half_life_days[meta.key]"
                :min="1"
                :max="90"
                integer
                button-size="22px"
                input-width="34px"
              />
              天
            </span>
          </div>
        </div>

        <van-button
          block
          round
          type="primary"
          :loading="scoringSaving"
          class="sheet__submit"
          @click="saveScoring"
        >
          保存偏好
        </van-button>
      </div>
    </van-popup>

    <!-- password popup -->
    <van-popup v-model:show="passwordPopup" position="bottom" round closeable>
      <div class="sheet">
        <h3 class="sheet__title">修改密码</h3>
        <label class="sheet-label">
          当前密码
          <input
            v-model="passwordForm.old_password"
            type="password"
            autocomplete="current-password"
            class="sheet-input"
            placeholder="请输入当前密码"
          />
        </label>
        <label class="sheet-label">
          新密码
          <input
            v-model="passwordForm.new_password"
            type="password"
            autocomplete="new-password"
            class="sheet-input"
            placeholder="至少 8 位"
          />
        </label>
        <label class="sheet-label">
          确认新密码
          <input
            v-model="passwordForm.confirm_password"
            type="password"
            autocomplete="new-password"
            class="sheet-input"
            placeholder="再次输入新密码"
          />
        </label>
        <van-button
          block
          round
          type="primary"
          :loading="passwordSaving"
          class="sheet__submit"
          @click="savePassword"
        >
          更新密码
        </van-button>
      </div>
    </van-popup>
  </div>
</template>

<style scoped>
.settings-page {
  background:
    linear-gradient(180deg, #0e2439 0, #0e2439 224px, transparent 224px),
    var(--rs-bg);
}

.settings-hero {
  padding-bottom: 22px;
}

.profile-card {
  display: flex;
  align-items: center;
  gap: 13px;
  margin: -10px 12px 0;
  padding: 16px;
}

.profile-card__avatar {
  display: grid;
  place-items: center;
  flex: none;
  width: 52px;
  height: 52px;
  border-radius: 16px;
  background: linear-gradient(145deg, #1b3a57, #0e2439);
  color: #fff;
  font-size: 21px;
  font-weight: 700;
  box-shadow: inset 0 -8px 14px rgba(0, 0, 0, 0.18);
}

.profile-card__body {
  flex: 1;
  min-width: 0;
}

.profile-card__name-row {
  display: flex;
  align-items: center;
  gap: 7px;
}

.profile-card__name-row h2 {
  margin: 0;
  font-size: 17px;
  font-weight: 700;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.profile-card__email {
  margin: 5px 0 0;
  font-size: 11.5px;
  color: var(--rs-muted);
}

.profile-card__since {
  margin: 3px 0 0;
  font-size: 10px;
  color: var(--rs-muted);
  opacity: 0.8;
}

.profile-card__edit {
  flex: none;
  padding: 5px 12px;
  border: 1px solid var(--rs-line);
  border-radius: 999px;
  background: #fff;
  font-size: 11px;
  font-weight: 600;
  color: var(--rs-ink-soft);
  cursor: pointer;
}

.settings-group {
  overflow: hidden;
}

.settings-row {
  display: flex;
  align-items: center;
  gap: 11px;
  width: 100%;
  padding: 13px 14px;
  border: none;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.settings-row + .settings-row {
  border-top: 1px solid var(--rs-line);
}

.settings-row:active {
  background: #fafcff;
}

.settings-row__icon {
  display: grid;
  place-items: center;
  flex: none;
  width: 32px;
  height: 32px;
  border-radius: 10px;
}

.settings-row__icon--amber {
  background: var(--rs-accent-soft);
  color: var(--rs-accent);
}

.settings-row__icon--blue {
  background: #eef4ff;
  color: #2855a8;
}

.settings-row__icon--green {
  background: var(--rs-down-soft);
  color: var(--rs-down);
}

.settings-row__icon--slate {
  background: var(--rs-neutral-soft);
  color: var(--rs-neutral);
}

.settings-row__body {
  flex: 1;
  min-width: 0;
}

.settings-row__label {
  display: block;
  font-size: 13px;
  font-weight: 600;
  color: var(--rs-ink);
}

.settings-row__value {
  display: block;
  margin-top: 3px;
  font-size: 10.5px;
  line-height: 1.55;
  color: var(--rs-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.settings-row__arrow {
  flex: none;
  color: #b7c2cf;
}

.about-card {
  padding: 16px;
}

.about-card__head {
  display: flex;
  align-items: center;
  gap: 11px;
}

.about-card__mark {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  border-radius: 11px;
  background: linear-gradient(145deg, #1b3a57, #0e2439);
  color: #fff;
  font-size: 18px;
  font-weight: 800;
}

.about-card__head h3 {
  margin: 0;
  font-size: 13.5px;
  font-weight: 700;
}

.about-card__head p {
  margin: 3px 0 0;
  font-size: 10px;
  color: var(--rs-muted);
  letter-spacing: 0.06em;
}

.about-card__text {
  margin: 13px 0 0;
  font-size: 11.5px;
  line-height: 1.75;
  color: var(--rs-ink-soft);
}

.about-card__disclaimer {
  margin: 10px 0 0;
  padding-top: 10px;
  border-top: 1px dashed var(--rs-line);
  font-size: 10px;
  line-height: 1.7;
  color: var(--rs-muted);
}

.settings-logout {
  padding: 20px 14px calc(30px + env(safe-area-inset-bottom));
}

.sheet {
  padding: 22px 20px calc(24px + env(safe-area-inset-bottom));
}

.sheet--scroll {
  max-height: 84vh;
  overflow-y: auto;
}

.sheet__title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
}

.sheet__subtitle {
  margin: 6px 0 18px;
  font-size: 11.5px;
  line-height: 1.7;
  color: var(--rs-muted);
}

.sheet__submit {
  height: 44px;
  margin-top: 22px;
  font-size: 14px;
  font-weight: 600;
}

.sheet-label {
  display: block;
  margin: 14px 0 0;
  font-size: 12px;
  font-weight: 600;
  color: var(--rs-ink-soft);
}

.sheet-input {
  display: block;
  width: 100%;
  margin-top: 7px;
  padding: 11px 13px;
  border: 1px solid var(--rs-line);
  border-radius: 10px;
  background: #fbfcfe;
  font-size: 14px;
  outline: none;
}

.sheet-input:focus {
  border-color: var(--rs-accent);
  background: #fff;
}

.sheet-note {
  margin: 12px 0 0;
  font-size: 11px;
  color: var(--rs-muted);
}

.scoring-block {
  padding: 14px 0;
  border-top: 1px dashed var(--rs-line);
}

.scoring-block:first-of-type {
  border-top: none;
  padding-top: 4px;
}

.scoring-block__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 8px;
}

.scoring-block__label {
  font-size: 13px;
  font-weight: 700;
}

.scoring-block__weight {
  font-size: 14px;
  font-weight: 700;
  color: var(--rs-accent);
}

.scoring-block__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 9px;
}

.scoring-block__hint {
  font-size: 10px;
  color: var(--rs-muted);
}

.scoring-block__half-life {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  flex: none;
  font-size: 10px;
  color: var(--rs-muted);
}
</style>
