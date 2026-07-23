<template>
  <div class="checkout-history-page">
    <div class="card-container page-card">
      <div class="page-header">
        <div>
          <h1 class="vp-page-title">结算订单历史</h1>
          <p class="vp-page-subtitle">查询已创建的收银订单记录</p>
        </div>
        <div class="header-actions">
          <el-button type="primary" text :icon="ArrowLeft" @click="router.push('/checkout')">
            返回结算页
          </el-button>
        </div>
      </div>

      <div class="summary-strip vp-glass">
        <div class="summary-cell">
          <small>筛选结果订单</small>
          <strong class="vp-num">{{ pagination.total }}</strong>
        </div>
        <div class="summary-cell">
          <small>本页订单总额</small>
          <strong class="vp-num">¥ {{ summaryPageAmount }}</strong>
        </div>
        <div class="summary-cell">
          <small>本页待支付</small>
          <strong class="vp-num">{{ summaryPendingCount }}</strong>
        </div>
      </div>

      <div class="filter-bar">
        <el-date-picker
          v-model="filter.start_date"
          class="filter-date"
          type="date"
          placeholder="开始日期"
          value-format="YYYY-MM-DD"
        />
        <el-date-picker
          v-model="filter.end_date"
          class="filter-date"
          type="date"
          placeholder="结束日期"
          value-format="YYYY-MM-DD"
        />
        <el-select v-model="filter.status" class="filter-status" placeholder="订单状态" clearable>
          <el-option label="全部" value="" />
          <el-option label="待支付" value="pending" />
          <el-option label="已支付" value="paid" />
          <el-option label="已过期" value="expired" />
        </el-select>
        <el-button type="primary" :icon="Search" @click="handleSearch">查询</el-button>
      </div>

      <el-table v-loading="loading" :data="orders" stripe style="width: 100%">
        <el-table-column prop="order_uuid" label="订单编号" width="150">
          <template #default="{ row }">
            {{ orderNumber(row.order_uuid) }}
          </template>
        </el-table-column>
        <el-table-column prop="amount" label="金额" width="120" align="right">
          <template #default="{ row }">
            <span class="vp-num amount-num">¥ {{ Number(row.amount).toFixed(2) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="120">
          <template #default="{ row }">
            <span
              class="vp-pill"
              :class="{
                'vp-pill--success': row.status === 'paid',
                'vp-pill--warning': row.status === 'pending',
                'vp-pill--danger': row.status === 'expired',
              }"
            >
              {{ statusText(row.status) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="item_count" label="商品数" width="90" />
        <el-table-column prop="created_at" label="创建时间" width="170">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column prop="paid_at" label="支付时间" width="170">
          <template #default="{ row }">
            {{ formatTime(row.paid_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="190" fixed="right" align="center">
          <template #default="{ row }">
            <div class="table-actions vp-table-action-safe-area">
              <el-button
                class="vp-table-action-button is-primary-action"
                size="small"
                :icon="View"
                @click="openDetail(row)"
                >查看</el-button
              >
              <el-dropdown
                trigger="click"
                placement="bottom-end"
                popper-class="checkout-row-actions-popper"
              >
                <el-button
                  class="vp-table-action-button row-actions-more"
                  size="small"
                  aria-label="更多操作"
                >
                  更多<el-icon class="el-icon--right"><ArrowDown /></el-icon>
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item
                      v-if="row.status === 'pending'"
                      :icon="CircleClose"
                      @click="closeOrder(row)"
                      >结束支付</el-dropdown-item
                    >
                    <el-dropdown-item
                      :icon="Delete"
                      class="is-danger-item"
                      :divided="row.status === 'pending'"
                      @click="deleteOrder(row)"
                      >删除</el-dropdown-item
                    >
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </template>
        </el-table-column>
        <template #empty>
          <EmptyState
            :icon="Tickets"
            title="暂无结算订单"
            description="调整筛选条件或日期范围后重新查询"
          />
        </template>
      </el-table>

      <div class="pagination-bar">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.page_size"
          :total="pagination.total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @change="handleSearch"
        />
      </div>
    </div>

    <el-dialog
      v-model="detailVisible"
      title="订单详情"
      width="560px"
      append-to-body
      destroy-on-close
    >
      <el-skeleton v-if="detailLoading" :rows="6" animated />
      <div v-else-if="detailOrder" class="detail-body">
        <div class="detail-meta">
          <div>
            <span>订单编号</span><b>{{ orderNumber(detailOrder.order_uuid) }}</b>
          </div>
          <div>
            <span>订单状态</span>
            <span
              class="vp-pill"
              :class="{
                'vp-pill--success': detailOrder.status === 'paid',
                'vp-pill--warning': detailOrder.status === 'pending',
                'vp-pill--danger': detailOrder.status === 'expired',
              }"
              >{{ statusText(detailOrder.status) }}</span
            >
          </div>
          <div>
            <span>商品总数</span><b>{{ detailOrder.item_count }} 件</b>
          </div>
          <div>
            <span>应付金额</span><b>¥ {{ Number(detailOrder.amount).toFixed(2) }}</b>
          </div>
          <div>
            <span>创建时间</span><b>{{ formatTime(detailOrder.created_at) }}</b>
          </div>
          <div>
            <span>支付时间</span><b>{{ formatTime(detailOrder.paid_at) }}</b>
          </div>
        </div>
        <el-divider />
        <h4>商品明细</h4>
        <el-table :data="detailOrder.items" stripe size="small">
          <el-table-column prop="class_id" label="类别 ID" width="90" />
          <el-table-column prop="name" label="商品名" show-overflow-tooltip />
          <el-table-column prop="count" label="数量" width="80" />
          <el-table-column label="小计" width="100">
            <template #default="{ row }">¥ {{ Number(row.subtotal).toFixed(2) }}</template>
          </el-table-column>
        </el-table>
      </div>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
        <el-button
          v-if="detailOrder?.status === 'pending'"
          type="primary"
          @click="continuePay(detailOrder)"
        >
          继续支付
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, reactive, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowDown,
  ArrowLeft,
  CircleClose,
  Delete,
  Search,
  Tickets,
  View,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import EmptyState from '@/components/EmptyState.vue'
import {
  closeMockPaymentOrderApi,
  deleteMockPaymentOrderApi,
  getMockPaymentOrderDetailApi,
  getMockPaymentOrderHistoryApi,
} from '@/api/checkout'

const router = useRouter()
const loading = ref(false)
const detailLoading = ref(false)
const orders = ref([])
const detailVisible = ref(false)
const detailOrder = ref(null)

const filter = reactive({
  start_date: '',
  end_date: '',
  status: '',
})

const pagination = reactive({
  page: 1,
  page_size: 20,
  total: 0,
})

// 统计带全部由现有列表/分页状态推导，不发新请求：
// 总单数取筛选结果总数 pagination.total，金额与待支付数按当前页订单汇总。
const summaryPageAmount = computed(() =>
  orders.value.reduce((sum, order) => sum + Number(order.amount || 0), 0).toFixed(2),
)
const summaryPendingCount = computed(
  () => orders.value.filter((order) => order.status === 'pending').length,
)

function orderNumber(uuid) {
  if (!uuid) return '--'
  return `VP-${uuid.slice(0, 8).toUpperCase()}`
}

function statusText(status) {
  return { pending: '待支付', paid: '已支付', expired: '已过期' }[status] || status
}

function formatTime(value) {
  if (!value) return '-'
  return new Date(value).toLocaleString()
}

async function handleSearch() {
  loading.value = true
  try {
    const params = {
      page: pagination.page,
      page_size: pagination.page_size,
    }
    if (filter.start_date) params.start_date = filter.start_date
    if (filter.end_date) params.end_date = filter.end_date
    if (filter.status) params.status = filter.status

    const res = await getMockPaymentOrderHistoryApi(params)
    orders.value = res.items || []
    pagination.total = res.total || 0
  } catch {
    ElMessage.error('查询订单历史失败')
    orders.value = []
    pagination.total = 0
  } finally {
    loading.value = false
  }
}

async function openDetail(row) {
  detailVisible.value = true
  detailLoading.value = true
  try {
    detailOrder.value = await getMockPaymentOrderDetailApi(row.order_uuid)
  } catch {
    ElMessage.error('获取订单详情失败')
    detailOrder.value = null
  } finally {
    detailLoading.value = false
  }
}

async function continuePay(row) {
  try {
    const order = await getMockPaymentOrderDetailApi(row.order_uuid)
    if (order.status !== 'pending') {
      ElMessage.warning('该订单已无法继续支付')
      return
    }
    sessionStorage.setItem('visionpay-payment-order', JSON.stringify(order))
    const cart = {
      items: (order.items || []).map((item) => ({
        classId: item.class_id,
        name: item.name,
        quantity: item.count,
        unitPrice: item.unit_price,
        subtotal: item.subtotal,
      })),
      itemCount: order.item_count,
      totalPrice: order.amount,
      currency: order.currency,
    }
    sessionStorage.setItem('visionpay-checkout-order', JSON.stringify(cart))
    router.push({ path: '/checkout/payment', query: { token: order.payment_token } })
  } catch {
    ElMessage.error('进入支付页失败')
  }
}

async function deleteOrder(row) {
  try {
    await ElMessageBox.confirm(
      `确定删除订单 ${orderNumber(row.order_uuid)} 吗？删除后无法恢复。`,
      '删除确认',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
        customClass: 'app-confirm-dialog',
      },
    )
  } catch {
    return
  }
  try {
    await deleteMockPaymentOrderApi(row.order_uuid)
    ElMessage.success('删除成功')
    await handleSearch()
  } catch {
    ElMessage.error('删除失败')
  }
}

async function closeOrder(row) {
  try {
    await ElMessageBox.confirm(
      `确定结束订单 ${orderNumber(row.order_uuid)} 的待支付状态吗？结束后该支付二维码将立即失效。`,
      '结束支付确认',
      { confirmButtonText: '结束支付', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  try {
    const closedOrder = await closeMockPaymentOrderApi(row.order_uuid)
    ElMessage.success('订单已结束')
    if (detailOrder.value?.order_uuid === row.order_uuid) {
      detailOrder.value = { ...detailOrder.value, ...closedOrder }
    }
    await handleSearch()
  } catch {
    ElMessage.error('结束订单失败，请刷新后重试')
  }
}

onMounted(() => {
  handleSearch()
})
</script>

<style lang="scss" scoped>
.checkout-history-page {
  padding: 24px;
  background: $bg-color;

  .page-card {
    padding: $spacing-lg;
  }

  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 20px;

    .header-actions {
      display: flex;
      align-items: center;
      gap: 12px;
    }
  }

  .filter-bar {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 16px;
    flex-wrap: wrap;

    .filter-date {
      width: 150px;
    }

    .filter-status {
      width: 140px;
    }
  }

  // 轻量统计带：玻璃通栏 + 1px 分隔线，数据全由当前列表推导；
  // 深色下叠一层微弱品牌渐变底纹（参照 HistoryPage summary-hero，保持轻量无图标）。
  .summary-strip {
    display: flex;
    align-items: stretch;
    margin-bottom: 16px;
    padding: 4px 8px;

    html.dark & {
      background:
        linear-gradient(
          135deg,
          color-mix(in srgb, var(--vp-primary) 9%, transparent),
          color-mix(in srgb, var(--vp-accent-cyan) 6%, transparent)
        ),
        var(--vp-surface);
    }

    .summary-cell {
      flex: 1;
      min-width: 0;
      display: flex;
      flex-direction: column;
      gap: 2px;
      padding: 8px 20px;

      small {
        color: $text-secondary;
        font-size: 12px;
        font-weight: 500;
      }

      strong {
        color: $text-primary;
        font-family: var(--vp-font-mono);
        font-size: 20px;
        font-weight: 700;
        line-height: 1.3;
      }
    }

    .summary-cell + .summary-cell {
      border-left: 1px solid $border-color;
    }
  }

  .amount-num {
    font-family: var(--vp-font-mono);
    font-weight: 500;
  }

  .pagination-bar {
    display: flex;
    justify-content: flex-end;
    margin-top: 16px;
  }

  .table-actions {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
  }

  .detail-body {
    .detail-meta {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;

      > div {
        display: flex;
        flex-direction: column;
        gap: 4px;

        span {
          color: $text-secondary;
          font-size: 12px;
        }

        b {
          color: $text-primary;
          font-size: 14px;
          font-weight: 600;
        }
      }
    }

    h4 {
      margin: 0 0 12px;
      color: $text-primary;
      font-size: 15px;
    }
  }
}

/* 行操作「更多」菜单：圆角卡片化，危险项走语义红（与数据集页同一模式）。 */
:global(.checkout-row-actions-popper) {
  padding: 0 !important;
  overflow: hidden;
  border: 1px solid var(--vp-border) !important;
  border-radius: 12px !important;
  background: var(--vp-surface) !important;
  box-shadow: var(--vp-shadow-lg) !important;
}

:global(.checkout-row-actions-popper .el-popper__arrow) {
  display: none !important;
}

:global(.checkout-row-actions-popper .el-dropdown-menu) {
  padding: 5px;
  border-radius: inherit;
}

:global(.checkout-row-actions-popper .el-dropdown-menu__item) {
  min-height: 34px;
  padding: 0 10px;
  gap: 8px;
  border-radius: 8px;
  font-size: 13px;
}

:global(.checkout-row-actions-popper .el-dropdown-menu__item.is-danger-item) {
  color: var(--vp-danger);
}

:global(.checkout-row-actions-popper .el-dropdown-menu__item.is-danger-item:hover),
:global(.checkout-row-actions-popper .el-dropdown-menu__item.is-danger-item:focus) {
  color: var(--vp-danger) !important;
  background: var(--vp-danger-bg) !important;
}

:global(.checkout-row-actions-popper .el-dropdown-menu__item--divided) {
  margin-top: 4px;
  border-top-color: var(--vp-border);
}

:global(html.dark .checkout-history-page) {
  background: $bg-color;
}
</style>
