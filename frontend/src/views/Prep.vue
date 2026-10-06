<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const tree = ref<any[]>([])
const data = ref<any>(null)
const runs = ref<any[]>([])
const orders = ref<any[]>([])
const selectedId = ref<number | null>(null)
const generating = ref(false)
const loadError = ref('')
const hasRun = ref(false)

async function loadRun(id: number) {
  // 纯读旧单：后端只返回生成当时的快照，定额对不上时给 dirty，绝不改数字
  data.value = await api(`/prep/run/${id}`)
  selectedId.value = id
  hasRun.value = true
}

async function refreshLatest() {
  try {
    runs.value = await api('/prep/runs?order_id=1')
    if (runs.value.length) await loadRun(runs.value[0].id)
    else hasRun.value = false
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : String(e)
  }
}

async function run() {
  // 唯一生成入口：按当下定额/结存落一张新单，旧单不受影响
  generating.value = true
  try {
    const created = await api('/prep/run?order_id=1', { method: 'POST' })
    await refreshLatest()
    await loadRun(created.id)
  } finally {
    generating.value = false
  }
}

onMounted(async () => {
  const [bomTree, orderList] = await Promise.all([api('/bom/tree'), api('/orders')])
  tree.value = bomTree
  orders.value = orderList
  await refreshLatest()
})
</script>
<template>
  <h1>备料工作台</h1>
  <p class="sub">左 BOM 树 · 中备料表（数字钉死生成当时） · 右缺料便利贴 · 顶栏订单芯片</p>
  <div class="kp-chips" style="margin-bottom:0.75rem" v-if="orders.length">
    <span v-for="o in orders" :key="o.id" class="kp-chip" style="cursor:default">
      {{ o.code }} · {{ o.outlet }}
    </span>
    <select v-if="runs.length" :value="selectedId ?? undefined"
            @change="loadRun(Number(($event.target as HTMLSelectElement).value))"
            style="margin-left:0.5rem">
      <option v-for="(r, i) in runs" :key="r.id" :value="r.id">
        #{{ r.id }} · {{ r.created_at?.replace('T', ' ').slice(0, 16) }}{{ r.dirty ? ' · 定额已变' : '' }}{{ i === 0 ? '（最新）' : '' }}
      </option>
    </select>
  </div>
  <button class="btn" :disabled="generating" @click="run">
    {{ generating ? '生成中…' : (hasRun ? '按当下定额重新生成（新单）' : '生成备料单') }}
  </button>
  <p v-if="loadError" class="sub" style="color:var(--kp-bad)">{{ loadError }}</p>

  <div v-if="data?.dirty" class="card" style="margin:0.75rem 0;border-color:var(--kp-accent)">
    <span class="badge badge-warn">⚠ 定额已变 · 旧单数字钉死</span>
    <span style="margin-left:0.5rem;font-size:0.85rem">
      {{ data.dirty_reasons?.[0] || '当下定额已与本单对不上' }}
    </span>
  </div>

  <div class="kp-workbench" style="margin-top:0.85rem">
    <aside class="kp-bom-tree">
      <h2>菜品 / BOM（当下定额）</h2>
      <div v-for="d in tree" :key="d.code" class="kp-dish-node">
        <strong>{{ d.dish }}</strong>
        <span style="font-size:0.7rem;color:#8a8078">{{ d.code }}</span>
        <ul>
          <li v-for="(c,i) in d.children" :key="i">{{ c.ingredient }} · {{ c.qty }} {{ c.unit }}</li>
        </ul>
      </div>
    </aside>
    <section class="kp-worksheet">
      <h2 v-if="!hasRun">尚未生成备料单</h2>
      <template v-else-if="data">
        <h2>
          备料单 #{{ data.id }}
          <span v-if="data.dirty" class="badge badge-warn" style="font-size:0.7rem">脏</span>
        </h2>
        <p class="sub" style="margin:0 0 0.5rem">生成于 {{ data.created_at?.replace('T', ' ').slice(0, 16) }} · 需求/库存/缺料均为当时快照</p>
        <table>
          <thead><tr><th>原料</th><th>需求</th><th>库存</th><th>单位</th></tr></thead>
          <tbody>
            <tr v-for="l in data.prep_lines" :key="l.ingredient_id">
              <td>{{ l.ingredient_name }}</td><td>{{ l.need_qty }}</td><td>{{ l.stock_qty }}</td><td>{{ l.unit }}</td>
            </tr>
          </tbody>
        </table>
      </template>
      <p v-else class="sub">加载中…</p>
    </section>
    <aside class="kp-shortage-sticky">
      <h2>⚠ 缺料便利贴</h2>
      <template v-if="data">
        <div v-for="r in data.shortages" :key="r.ingredient_id" class="kp-shortage-item">
          <span>{{ r.ingredient_name }}</span>
          <span class="kp-qty">−{{ r.shortage }} {{ r.unit }}</span>
        </div>
        <p v-if="!data.shortages?.length" style="font-size:0.8rem;margin:0.5rem 0 0">暂无缺料</p>
      </template>
      <p v-else style="font-size:0.8rem;margin:0.5rem 0 0">点击「生成备料单」后出缺料</p>
    </aside>
  </div>
</template>
