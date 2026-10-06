<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, ApiError } from '../api'
const rows = ref<any[]>([])
const stats = ref<any>({})
const dirty = ref(false)
const dirtyReasons = ref<string[]>([])
const noRun = ref(false)

onMounted(async () => {
  try {
    const res = await api('/prep/shortages?order_id=1')
    rows.value = res.shortages
    stats.value = res.stats
    dirty.value = !!res.dirty
    dirtyReasons.value = res.dirty_reasons || []
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) noRun.value = true
    else throw e
  }
})
</script>
<template>
  <h1>缺料便利贴</h1>
  <p class="sub">数字取自最近一张备料单生成当时的快照（shortage = need − stock，仅正数）</p>

  <div v-if="noRun" class="card">
    尚未生成备料单：请到「备料工作台」点击「生成备料单」。读取旧单不会自动出新单。
  </div>

  <template v-else>
    <div v-if="dirty" class="card" style="margin-bottom:0.85rem;border-color:var(--kp-accent)">
      <span class="badge badge-warn">⚠ 定额已变 · 缺料为旧单快照</span>
      <span style="margin-left:0.5rem;font-size:0.85rem">
        {{ dirtyReasons[0] || '当下定额已与该单对不上；如需按新定额计算，请重新生成新单' }}
      </span>
    </div>
    <div class="kp-shortage-sticky" style="max-width:360px;transform:rotate(-1deg);margin-bottom:1rem">
      <h2>⚠ 缺料 {{ stats.shortage_count }} · 合计 {{ stats.total_shortage_qty }}</h2>
      <div v-for="r in rows" :key="r.ingredient_id" class="kp-shortage-item">
        <span>{{ r.ingredient_name }}</span>
        <span class="kp-qty">−{{ r.shortage }} {{ r.unit }}</span>
      </div>
    </div>
    <div class="card">
      <table>
        <thead><tr><th>原料</th><th>需求</th><th>库存</th><th>缺料</th><th>单位</th></tr></thead>
        <tbody>
          <tr v-for="r in rows" :key="r.ingredient_id">
            <td>{{ r.ingredient_name }}</td><td>{{ r.need_qty }}</td><td>{{ r.stock_qty }}</td>
            <td><span class="badge badge-bad">{{ r.shortage }}</span></td><td>{{ r.unit }}</td>
          </tr>
        </tbody>
      </table>
      <p v-if="!rows.length" class="sub" style="margin:0.5rem 0 0">该单生成时暂无缺料</p>
    </div>
  </template>
</template>
