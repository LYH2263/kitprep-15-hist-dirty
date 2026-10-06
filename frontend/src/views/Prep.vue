<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const tree = ref<any[]>([])
const data = ref<any>(null)
const shortages = ref<any[]>([])
const orders = ref<any[]>([])
const loading = ref(false)

async function loadLatest() {
  // 读旧单：只读快照，不会落新单、不改旧数字
  const res = await api('/prep/latest?order_id=1')
  data.value = res.exists ? res : null
  shortages.value = res.exists ? (res.shortages || []) : []
}

async function run() {
  loading.value = true
  try {
    // 显式生成：仅此动作按当前定额/结存落一张新单
    data.value = await api('/prep/run?order_id=1', { method: 'POST' })
    shortages.value = data.value.shortages || []
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  tree.value = await api('/bom/tree')
  orders.value = await api('/orders')
  await loadLatest()
})
</script>
<template>
  <h1>备料工作台</h1>
  <p class="sub">左 BOM 树 · 中备料表 · 右缺料便利贴 · 顶栏订单芯片</p>
  <div class="kp-chips" style="margin-bottom:0.75rem" v-if="orders.length">
    <span v-for="o in orders" :key="o.id" class="kp-chip" style="cursor:default">
      {{ o.code }} · {{ o.outlet }}
    </span>
  </div>
  <div class="kp-actions" style="display:flex;align-items:center;gap:0.6rem">
    <button class="btn" :disabled="loading" @click="run">
      {{ data ? '按当前定额重新生成' : '生成备料单' }}
    </button>
    <span v-if="data?.created_at" style="font-size:0.75rem;color:#8a8078">
      当前单 #{{ data.id }} · 生成于 {{ data.created_at }}
    </span>
  </div>

  <!-- 脏标：定额/结存与旧单对不上，只提示，绝不改旧数字 -->
  <div v-if="data?.stale?.is_stale" class="kp-stale-banner" role="alert">
    <strong>⚠ 本单数据已过期（脏标）</strong>
    <ul style="margin:0.3rem 0 0 1.1rem">
      <li v-if="data.stale.qty_changed.length">
        定额/订单已变更，需求与缺料与旧单对不上：
        <span v-for="d in data.stale.qty_changed" :key="'q'+d.ingredient_id" class="kp-stale-item">
          {{ d.ingredient_name }}（旧需求 {{ d.snapshot_need_qty }} → 当前 {{ d.current_need_qty }}）
        </span>
      </li>
      <li v-if="data.stale.stock_changed.length">
        结存已变更，本单缺料数字不动：
        <span v-for="d in data.stale.stock_changed" :key="'s'+d.ingredient_id" class="kp-stale-item">
          {{ d.ingredient_name }}（结存 {{ d.snapshot_stock_qty }} → {{ d.current_stock_qty }}，旧缺料 {{ d.snapshot_shortage }} → 当前 {{ d.current_shortage }}）
        </span>
      </li>
    </ul>
    <span style="display:inline-block;margin-top:0.3rem;font-size:0.8rem">
      旧单数字保持不变；需要新数字请点上方按钮重新生成。
    </span>
  </div>

  <div v-if="!data" class="card" style="margin-top:0.85rem;padding:1rem">
    该订单还没有备料单，点「生成备料单」按当前定额与结存出一张新单。
  </div>

  <div class="kp-workbench" style="margin-top:0.85rem">
    <aside class="kp-bom-tree">
      <h2>菜品 / BOM</h2>
      <div v-for="d in tree" :key="d.code" class="kp-dish-node">
        <strong>{{ d.dish }}</strong>
        <span style="font-size:0.7rem;color:#8a8078">{{ d.code }}</span>
        <ul>
          <li v-for="(c,i) in d.children" :key="i">{{ c.ingredient }} · {{ c.qty }} {{ c.unit }}</li>
        </ul>
      </div>
    </aside>
    <section class="kp-worksheet" v-if="data">
      <h2>备料单 · {{ data.order?.code }} · {{ data.order?.outlet }}</h2>
      <table>
        <thead><tr><th>原料</th><th>需求</th><th>库存</th><th>单位</th></tr></thead>
        <tbody>
          <tr v-for="l in data.prep_lines" :key="l.ingredient_id">
            <td>{{ l.ingredient_name }}</td><td>{{ l.need_qty }}</td><td>{{ l.stock_qty }}</td><td>{{ l.unit }}</td>
          </tr>
        </tbody>
      </table>
    </section>
    <aside class="kp-shortage-sticky">
      <h2>⚠ 缺料便利贴</h2>
      <div v-for="r in shortages" :key="r.ingredient_id" class="kp-shortage-item">
        <span>{{ r.ingredient_name }}</span>
        <span class="kp-qty">−{{ r.shortage }} {{ r.unit }}</span>
      </div>
      <p v-if="!shortages.length" style="font-size:0.8rem;margin:0.5rem 0 0">暂无缺料</p>
    </aside>
  </div>
</template>
