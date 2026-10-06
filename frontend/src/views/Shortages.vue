<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const rows = ref<any[]>([])
const stats = ref<any>({})
const stale = ref<any>(null)
const exists = ref(false)
onMounted(async () => {
  // 读旧单缺料：只读快照，缺料数字钉死在生成当时
  const res = await api('/prep/shortages?order_id=1')
  exists.value = !!res.exists
  rows.value = res.shortages || []
  stats.value = res.stats || {}
  stale.value = res.stale
})
</script>
<template>
  <h1>缺料便利贴</h1>
  <p class="sub">shortage = need − stock（仅正数），数字钉死在备料单生成当时</p>
  <div v-if="!exists" class="card" style="margin-bottom:1rem;padding:1rem">
    该订单还没有备料单，缺料单无内容；请到备料工作台点「生成备料单」。
  </div>
  <div v-else-if="stale?.is_stale" class="kp-stale-banner" role="alert" style="margin-bottom:1rem">
    <strong>⚠ 旧单已过期（脏标）</strong>：当前定额/结存与本单对不上，以下缺料数字仍保持生成当时不变。
    <ul style="margin:0.3rem 0 0 1.1rem">
      <li v-if="stale.qty_changed.length">
        需求/缺料已对不上：
        <span v-for="d in stale.qty_changed" :key="'q'+d.ingredient_id" class="kp-stale-item">
          {{ d.ingredient_name }}（旧缺 {{ d.snapshot_shortage }} → 当前 {{ d.current_shortage }}）
        </span>
      </li>
      <li v-if="stale.stock_changed.length">
        结存已变，本单缺料数字不动：
        <span v-for="d in stale.stock_changed" :key="'s'+d.ingredient_id" class="kp-stale-item">
          {{ d.ingredient_name }}（旧缺 {{ d.snapshot_shortage }} → 当前 {{ d.current_shortage }}）
        </span>
      </li>
    </ul>
  </div>
  <div v-if="exists" class="kp-shortage-sticky" style="max-width:360px;transform:rotate(-1deg);margin-bottom:1rem">
    <h2>⚠ 缺料 {{ stats.shortage_count }} · 合计 {{ stats.total_shortage_qty }}</h2>
    <div v-for="r in rows" :key="r.ingredient_id" class="kp-shortage-item">
      <span>{{ r.ingredient_name }}</span>
      <span class="kp-qty">−{{ r.shortage }} {{ r.unit }}</span>
    </div>
  </div>
  <div v-if="exists" class="card">
    <table>
      <thead><tr><th>原料</th><th>需求</th><th>库存</th><th>缺料</th><th>单位</th></tr></thead>
      <tbody>
        <tr v-for="r in rows" :key="r.ingredient_id">
          <td>{{ r.ingredient_name }}</td><td>{{ r.need_qty }}</td><td>{{ r.stock_qty }}</td>
          <td><span class="badge badge-bad">{{ r.shortage }}</span></td><td>{{ r.unit }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
