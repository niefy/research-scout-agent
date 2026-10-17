<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const showTabbar = computed(() => route.meta.tabbar === true)
</script>

<template>
  <div class="app-shell">
    <router-view />
    <van-tabbar
      v-if="showTabbar"
      route
      safe-area-inset-bottom
      fixed
      placeholder
      active-color="#c2410c"
      inactive-color="#94a3b8"
      class="app-tabbar"
    >
      <van-tabbar-item replace to="/feed" icon="newspaper-o">首页</van-tabbar-item>
      <van-tabbar-item replace to="/watchlist" icon="star-o">自选</van-tabbar-item>
      <van-tabbar-item replace to="/authors" icon="friends-o">作者</van-tabbar-item>
      <van-tabbar-item replace to="/settings" icon="setting-o">我的</van-tabbar-item>
    </van-tabbar>
  </div>
</template>
