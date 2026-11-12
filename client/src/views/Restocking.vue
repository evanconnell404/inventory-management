<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error && !hasLoaded" class="error">{{ error }}</div>
    <div v-else>
      <div class="card budget-card">
        <div class="budget-header">
          <div>
            <div class="stat-label">{{ t('restocking.budget') }}</div>
            <div class="budget-value">{{ money(budget) }}</div>
          </div>
          <div class="budget-meta">{{ t('restocking.fullRestock', { amount: money(fullRestockCost) }) }}</div>
        </div>
        <input
          class="budget-slider"
          type="range"
          min="0"
          :max="fullRestockCost"
          step="100"
          :value="budget"
          :disabled="fullRestockCost <= 0"
          :aria-label="t('restocking.budgetSlider')"
          @input="onBudgetInput"
        />
        <div class="slider-scale">
          <span>{{ money(0) }}</span>
          <span>{{ money(fullRestockCost) }}</span>
        </div>
      </div>

      <div class="stats-grid">
        <div class="stat-card info">
          <div class="stat-label">{{ t('restocking.budget') }}</div>
          <div class="stat-value">{{ money(budget) }}</div>
        </div>
        <div class="stat-card warning">
          <div class="stat-label">{{ t('restocking.plannedSpend') }}</div>
          <div class="stat-value">{{ money(plan.total_cost) }}</div>
        </div>
        <div class="stat-card success">
          <div class="stat-label">{{ t('restocking.remaining') }}</div>
          <div class="stat-value">{{ money(plan.remaining_budget) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('restocking.leadTime') }}</div>
          <div class="stat-value">{{ t('restocking.days', { count: plan.lead_time_days }) }}</div>
        </div>
      </div>

      <div v-if="orderConfirmation" class="confirmation" role="status">
        <div>
          <strong>{{ t('restocking.orderPlaced', { id: orderConfirmation.id }) }}</strong>
          <span class="confirmation-detail">
            {{ t('restocking.expectedDelivery', { date: formatDate(orderConfirmation.expected_delivery) }) }}
          </span>
        </div>
        <router-link to="/orders" class="confirmation-link">{{ t('restocking.viewInOrders') }}</router-link>
      </div>
      <div v-if="error" class="error">{{ error }}</div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.recommended') }} ({{ items.length }})</h3>
          <button
            class="place-order-btn"
            type="button"
            :disabled="!canPlaceOrder"
            @click="placeOrder"
          >
            {{ submitting ? t('restocking.submitting') : t('restocking.placeOrder') }}
          </button>
        </div>

        <div v-if="items.length === 0" class="empty-state">{{ t('restocking.empty') }}</div>
        <div v-else class="table-container">
          <table>
            <thead>
              <tr>
                <th>{{ t('restocking.table.sku') }}</th>
                <th>{{ t('restocking.table.name') }}</th>
                <th>{{ t('restocking.table.trend') }}</th>
                <th class="num">{{ t('restocking.table.onHand') }}</th>
                <th class="num">{{ t('restocking.table.forecast') }}</th>
                <th class="num">{{ t('restocking.table.shortfall') }}</th>
                <th class="num">{{ t('restocking.table.unitCost') }}</th>
                <th class="num">{{ t('restocking.table.quantity') }}</th>
                <th class="num">{{ t('restocking.table.lineTotal') }}</th>
                <th class="num">{{ t('restocking.table.leadTime') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in items" :key="item.sku">
                <td><strong>{{ item.sku }}</strong></td>
                <td>{{ translateProductName(item.name) }}</td>
                <td>
                  <span :class="['badge', trendClass(item.trend)]">{{ t(`trends.${item.trend}`) }}</span>
                </td>
                <td class="num">{{ item.quantity_on_hand.toLocaleString() }}</td>
                <td class="num">{{ item.forecasted_demand.toLocaleString() }}</td>
                <td class="num">{{ item.shortfall.toLocaleString() }}</td>
                <td class="num">{{ money(item.unit_cost, 2) }}</td>
                <td class="num"><strong>{{ item.recommended_quantity.toLocaleString() }}</strong></td>
                <td class="num"><strong>{{ money(item.line_total) }}</strong></td>
                <td class="num">{{ t('restocking.days', { count: item.lead_time_days }) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'
import { formatCurrency, formatCurrencyWithDecimals } from '../utils/currency'

const DEBOUNCE_MS = 250

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency, currentLocale, translateProductName } = useI18n()

    const loading = ref(true)
    const hasLoaded = ref(false)
    const error = ref(null)
    const submitting = ref(false)
    const orderConfirmation = ref(null)

    const budget = ref(0)
    const fullRestockCost = ref(0)
    const plan = ref({ total_cost: 0, remaining_budget: 0, lead_time_days: 0, items: [] })

    const items = computed(() => plan.value.items || [])
    const canPlaceOrder = computed(() => items.value.length > 0 && !submitting.value)

    const money = (amount, decimals = 0) => {
      const value = Number(amount) || 0
      return decimals > 0
        ? formatCurrencyWithDecimals(value, currentCurrency.value, decimals)
        : formatCurrency(value, currentCurrency.value)
    }

    const trendClass = (trend) => ({ increasing: 'danger', stable: 'info', decreasing: 'success' }[trend] || 'info')

    const formatDate = (iso) => {
      const date = new Date(iso)
      if (isNaN(date.getTime())) return ''
      return date.toLocaleDateString(currentLocale.value === 'ja' ? 'ja-JP' : 'en-US', {
        year: 'numeric', month: 'short', day: 'numeric'
      })
    }

    // Each fetch gets an id; only the latest one may write state, so a slow
    // response for an older slider position cannot overwrite a newer one.
    let requestId = 0
    const fetchPlan = async () => {
      const id = ++requestId
      try {
        const result = await api.getRestockingRecommendations(budget.value)
        if (id !== requestId) return
        plan.value = result
        error.value = null
      } catch (err) {
        if (id !== requestId) return
        error.value = t('restocking.loadError')
        console.error('Restocking load error:', err)
      }
    }

    // The slider max is the cost of covering every shortfall. The API only
    // reports that figure, so a budget=0 call is used purely to read
    // full_restock_cost; it also tells us nothing is bought at zero.
    const loadFullCost = async () => {
      const base = await api.getRestockingRecommendations(0)
      fullRestockCost.value = base.full_restock_cost
      return base
    }

    const loadInitial = async () => {
      try {
        loading.value = true
        error.value = null
        await loadFullCost()
        // Start at roughly half so the first view shows a meaningful plan.
        budget.value = Math.round(fullRestockCost.value / 2 / 100) * 100
        await fetchPlan()
        hasLoaded.value = true
      } catch (err) {
        error.value = t('restocking.loadError')
        console.error('Restocking load error:', err)
      } finally {
        loading.value = false
      }
    }

    // Debounced so dragging the slider does not fire a request per pixel.
    let debounceTimer = null
    const onBudgetInput = (event) => {
      budget.value = Number(event.target.value)
      orderConfirmation.value = null
      clearTimeout(debounceTimer)
      debounceTimer = setTimeout(fetchPlan, DEBOUNCE_MS)
    }

    const placeOrder = async () => {
      if (!canPlaceOrder.value) return
      // Cancel any pending debounced fetch so the order matches what is on screen.
      clearTimeout(debounceTimer)
      submitting.value = true
      error.value = null
      try {
        const order = await api.createRestockingOrder({
          items: items.value.map(i => ({ sku: i.sku, quantity: i.recommended_quantity })),
          budget: budget.value
        })
        orderConfirmation.value = order
        // Stock/shortfalls changed server-side: refresh the max and the plan.
        await loadFullCost()
        budget.value = Math.min(budget.value, fullRestockCost.value)
        await fetchPlan()
      } catch (err) {
        error.value = err.response?.data?.detail || t('restocking.submitError')
        console.error('Place order error:', err)
      } finally {
        submitting.value = false
      }
    }

    onMounted(loadInitial)
    onBeforeUnmount(() => clearTimeout(debounceTimer))

    return {
      t,
      loading,
      hasLoaded,
      error,
      submitting,
      orderConfirmation,
      budget,
      fullRestockCost,
      plan,
      items,
      canPlaceOrder,
      money,
      trendClass,
      formatDate,
      onBudgetInput,
      placeOrder,
      translateProductName
    }
  }
}
</script>

<style scoped>
.budget-card {
  padding: 1.5rem;
}

.budget-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 1rem;
}

.budget-value {
  font-size: 3rem;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.025em;
  line-height: 1;
}

.budget-meta {
  color: #64748b;
  font-size: 0.875rem;
}

.budget-slider {
  width: 100%;
  accent-color: #0f172a;
  cursor: pointer;
}

.budget-slider:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.slider-scale {
  display: flex;
  justify-content: space-between;
  color: #64748b;
  font-size: 0.813rem;
  margin-top: 0.25rem;
}

.num {
  text-align: right;
}

.place-order-btn {
  background: #0f172a;
  color: white;
  border: none;
  border-radius: 8px;
  padding: 0.5rem 1.25rem;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.place-order-btn:hover:not(:disabled) {
  background: #1e293b;
}

.place-order-btn:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
}

.confirmation {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  background: #d1fae5;
  border: 1px solid #a7f3d0;
  color: #065f46;
  padding: 1rem;
  border-radius: 8px;
  margin-bottom: 1.25rem;
  font-size: 0.938rem;
}

.confirmation-detail {
  margin-left: 0.75rem;
}

.confirmation-link {
  color: #065f46;
  font-weight: 600;
  text-decoration: underline;
}

.empty-state {
  text-align: center;
  padding: 2rem;
  color: #64748b;
  font-size: 0.938rem;
}
</style>
