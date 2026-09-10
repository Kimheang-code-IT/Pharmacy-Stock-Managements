<script setup lang="ts">
import PosCartPanel from '~/components/pos/PosCartPanel.vue'
import PosCheckoutPanel from '~/components/pos/PosCheckoutPanel.vue'
import PosProductBrowser from '~/components/pos/PosProductBrowser.vue'
import { useAppHeader } from '~/composables/layout/useAppHeader'
import { useCurrencyRateDialog } from '~/composables/common/useCurrencyRateDialog'
import { usePosChrome } from '~/composables/layout/usePosChrome'
import { usePageSeo } from '~/composables/usePageSeo'
import { usePosCommands, useSettingsRepositories } from '~/repositories/index'
import type { PosCartLine } from '~/utils/pos/cart'
import {
  availableStockInUom,
  cartDiscountTotal,
  cartSubtotal,
  defaultLineUomFor,
  productImageUrl,
  roundMoney,
  uomOptionsFor,
} from '~/utils/pos/cart'
import {
  checkoutDeliveryFee,
  checkoutDepositTotal,
  checkoutDue,
  checkoutOutstanding,
  checkoutPaidNow,
  checkoutSaleNet,
  type CheckoutDebtRow,
} from '~/utils/pos/checkout'
import { printSaleInvoice, type PrintCurrencyChoice, type SaleInvoicePrintInput } from '~/utils/print/invoice'
import type { PrintPaperSize } from '~/utils/print/html'
import { conversionForUom, salePriceForUom } from '~/utils/stock/uom-conversions'

/**
 * POS workspace: product card grid + cart, then checkout (customer/summary/payment).
 * Submit auto-prints the bilingual invoice (no invoice dialog).
 */
type PosStep = 'cart' | 'checkout'

const store = useAppDataStore()
const preferences = usePreferencesStore()
const auth = useAuthStore()
const { t, locale } = useI18n()
const { clear } = useAppHeader()
const { hidePosAppHeader } = usePosChrome()
const posCommands = usePosCommands()
const { appInfo } = useSettingsRepositories()
const toast = useToast()

const shopName = ref('Yoeun Sokhon Pharmacy')
const step = ref<PosStep>('cart')
const search = ref('')
const categoryId = ref('')
const cart = ref<PosCartLine[]>([])
const customerId = ref<string | undefined>(undefined)
const customerName = ref('')
/** Read-only customer snapshot (phone/location live on the customer record;
 *  the checkout panel shows the Name selector only). */
const customerPhone = ref('')
const customerLocation = ref('')
const paymentMethod = ref<string>('Cash')
const paidInput = ref<number | undefined>()
const includedDebtIds = ref<string[]>([])
const deliveryPrice = ref(0)
/** Delivery destination captured in the checkout delivery-info dialog;
 *  prefills the post-sale Create Delivery Note (spec §2.1.9). */
const deliveryPhone = ref('')
const deliveryLocation = ref('')
const needsDelivery = ref(false)
const depositInput = ref(0)
const completing = ref(false)
// Document currency of THIS sale: USD prices convert at the entered rate
// when the cashier checks out in KHR (all amounts recorded in KHR).
const saleCurrency = ref<'USD' | 'KHR'>('USD')
const exchangeRateInput = ref<number | undefined>()
const saleRate = computed(() =>
  saleCurrency.value === 'KHR' ? Math.max(0, Number(exchangeRateInput.value || 0)) : 1)
/** USD-based cart amounts converted to the document currency. */
const docFromUsd = (value: number) => value * saleRate.value
/** Shared toggle logic: switching to KHR asks for the exchange rate through
 *  the shared dialog; cancelling keeps the previous currency. Switching
 *  currency also invalidates debt settling (debts keep their own currency). */
const {
  dialogOpen: exchangeRateDialogOpen,
  toggle: onSaleCurrencyChange,
  confirm: confirmSaleExchangeRate,
} = useCurrencyRateDialog({
  currency: saleCurrency,
  rate: exchangeRateInput,
  onChanged: () => {
    includedDebtIds.value = []
    depositInput.value = 0
  },
})
const lastSaleNo = ref('')
const lastSaleId = ref('')

onBeforeUnmount(() => {
  hidePosAppHeader.value = false
  clear()
})
usePageSeo({ title: () => t('app.pages.pos') })

watch(step, (value) => {
  hidePosAppHeader.value = value === 'checkout'
}, { immediate: true })

onMounted(async () => {
  void store.fetchList('products')
  void store.fetchList('customers')
  void store.fetchList('categories')
  try {
    const info = await appInfo.get()
    const name = String(info.businessName || info.applicationName || '').trim()
    if (name) shopName.value = name
  }
  catch {
    // Keep default shop name when settings are unavailable.
  }
})

const canOperate = computed(() =>
  auth.canAccessPage('pos.create')
  || auth.canAccessPage('pos.edit')
  || auth.canAccessPage('pos.access')
  || auth.canAccessPage('ALL_PAGES'))

const currency = computed(() => preferences.currency)

const categoryOptions = computed(() => [
  { label: t('app.pos.allCategories'), value: '' },
  ...store.list('categories')
    .filter(row => String(row.status || 'Active') !== 'Inactive')
    .map(row => ({ label: String(row.name || ''), value: String(row.id) })),
])

const products = computed(() => {
  const q = search.value.trim().toLowerCase()
  return store.list('products')
    .filter(row => String(row.status || 'Active') !== 'Inactive')
    .filter(row => !categoryId.value || String(row.categoryId) === categoryId.value)
    .filter((row) => {
      if (!q) return true
      return [row.name, row.barcode, row.code]
        .map(value => String(value || '').toLowerCase())
        .some(value => value.includes(q))
    })
})

/** Checkout customer options: label = name (displayed), phone/location ride
 *  on the item so the selector can search and show them (name · phone ·
 *  address) for faster selection. */
const customerOptions = computed(() =>
  store.list('customers')
    .filter(row => String(row.status) === 'Active')
    .map(row => ({
      label: String(row.name || ''),
      value: String(row.id),
      phone: String(row.phone || ''),
      location: String(row.location || row.address || ''),
      description: [row.phone, row.location || row.address]
        .map(part => String(part || '').trim())
        .filter(Boolean)
        .join(' · '),
    })),
)

const openDebts = computed<CheckoutDebtRow[]>(() => {
  if (!customerId.value) return []
  const salesById = Object.fromEntries(
    store.list('sales').map(row => [String(row.id), row]),
  )
  return store.list('customerDebts')
    .filter(row => String(row.customerId) === String(customerId.value))
    .filter(row => Number(row.remainingAmount || 0) > 0)
    .map((row) => {
      const sale = salesById[String(row.saleId)]
      return {
        ...row,
        id: String(row.id),
        date: String(row.date || '').slice(0, 10),
        invoiceNo: String(row.invoiceNo || sale?.invoiceNo || sale?.saleNo || ''),
        paidAmount: Number(row.paidAmount || 0),
        remainingAmount: Number(row.remainingAmount || 0),
        paymentMethod: String(row.paymentMethod || sale?.paymentMethod || '—'),
      }
    })
    .sort((a, b) => b.date.localeCompare(a.date))
})

const discountTotal = computed(() => cartDiscountTotal(cart.value))
const selectedDeposit = computed(() => checkoutDepositTotal(
  openDebts.value
    .filter(row => includedDebtIds.value.includes(row.id))
    .map(row => row.remainingAmount),
))
const appliedDeliveryPrice = computed(() =>
  checkoutDeliveryFee(needsDelivery.value, deliveryPrice.value))
// Delivery fee / deposit are typed in the document currency; cart prices are
// USD-based and convert at the sale rate.
const due = computed(() => checkoutDue(
  checkoutSaleNet(cartSubtotal(cart.value), discountTotal.value, 0) * saleRate.value
    + appliedDeliveryPrice.value,
  Number(depositInput.value || 0),
))
const isCredit = computed(() => paymentMethod.value === 'Credit')
/** Untouched Paid now pays the amount due in full — a walk-in cash sale
 *  submits without typing the tender (spec §5.11 walk-in rule). */
const paidAmount = computed(() =>
  checkoutPaidNow(paidInput.value, due.value, isCredit.value))
const outstandingAmount = computed(() => checkoutOutstanding(due.value, paidAmount.value))
// Previous debt (ខ្វះមុន): all open debts of the customer before this sale.
const previousDebtTotal = computed(() => roundMoney(
  openDebts.value.reduce((sum, row) => sum + row.remainingAmount, 0),
))
// Outstanding after this sale = current-sale outstanding + previous debt not
// settled at checkout (depositInput is the amount allocated to old debts).
const totalOutstanding = computed(() => roundMoney(
  outstandingAmount.value + Math.max(0, previousDebtTotal.value - Number(depositInput.value || 0)),
))

const dateLabel = computed(() => {
  const now = new Date()
  return new Intl.DateTimeFormat(locale.value === 'km' ? 'km-KH' : 'en-GB', {
    year: '2-digit',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(now)
})

const cashierName = computed(() => String(auth.user?.name || auth.user?.email || 'Cashier'))

const canCreateDelivery = computed(() =>
  auth.canAccessPage('delivery.create') || auth.canAccessPage('ALL_PAGES'))

/** Cart line UOM options: every Pricing row's Original UOM of that product. */
const lineUomOptions = uomOptionsFor

function addProduct(row: Record<string, unknown>) {
  const id = String(row.id)
  const stock = Number(row.quantity || 0)
  if (stock <= 0) {
    toast.add({ title: t('app.pos.outOfStock'), color: 'warning' })
    return
  }
  const existing = cart.value.find(line => line.productId === id)
  if (existing) {
    if (existing.quantity >= existing.availableStock) {
      toast.add({ title: t('app.pos.stockLimit'), color: 'warning' })
      return
    }
    existing.quantity += 1
    return
  }
  // Pre-select the product's **Default sale** Pricing row (else base/first,
  // spec §2.1.3 POS cart rule 2): price = that row's sale price, remaining
  // stock shown in the selected UOM (base stock ÷ conversion qty).
  const lineUom = defaultLineUomFor(row)
  const price = salePriceForUom(row, lineUom.uomId) ?? Number(row.salePrice || 0)
  cart.value.push({
    productId: id,
    name: String(row.name || ''),
    barcode: String(row.barcode || ''),
    uom: lineUom.uomSymbol,
    uomId: lineUom.uomId,
    factorToBase: lineUom.factorToBase,
    uomOptions: lineUomOptions(row),
    imageUrl: productImageUrl(row),
    availableStock: availableStockInUom(stock, lineUom.factorToBase),
    unitPrice: roundMoney(price),
    discountPercent: 0,
    quantity: 1,
  })
}

/**
 * Switch a cart line's UOM: price follows that Pricing row's sale price
 * (quantity stays in the Original UOM); remaining stock is shown in the
 * selected UOM (base stock ÷ conversion qty); line UOM symbol = Original UOM.
 */
function changeUom(productId: string, uomId: string) {
  const line = cart.value.find(item => item.productId === productId)
  if (!line || !uomId || line.uomId === uomId) return
  const product = products.value.find(row => String(row.id) === productId)
  if (!product) return
  const price = salePriceForUom(product, uomId)
  if (price == null) return
  const conversion = conversionForUom(product, uomId)
  const factor = conversion ? conversion.factorToBase : 1
  const symbol = conversion ? conversion.uomSymbol : String(product.uomSymbol || product.uom || '')
  line.uomId = uomId
  line.uom = symbol
  line.factorToBase = factor
  line.unitPrice = roundMoney(price)
  line.availableStock = availableStockInUom(product.quantity, factor)
}

function onSearchEnter() {
  const exact = products.value.find(row => String(row.barcode || '') === search.value.trim())
  if (exact) {
    addProduct(exact)
    search.value = ''
  }
}

function changeQty(productId: string, delta: number) {
  const line = cart.value.find(item => item.productId === productId)
  if (!line) return
  const next = Math.max(1, Math.min(line.availableStock, line.quantity + delta))
  line.quantity = next
}

function updatePrice(productId: string, unitPrice: number) {
  const line = cart.value.find(item => item.productId === productId)
  if (!line) return
  line.unitPrice = Math.max(0, roundMoney(unitPrice))
}

function updateDiscount(productId: string, discountPercent: number) {
  const line = cart.value.find(item => item.productId === productId)
  if (!line) return
  line.discountPercent = Math.min(100, Math.max(0, Number(discountPercent) || 0))
}

function removeLine(productId: string) {
  cart.value = cart.value.filter(line => line.productId !== productId)
}

function clearCart() {
  cart.value = []
  paidInput.value = undefined
  customerId.value = undefined
  customerName.value = ''
  customerPhone.value = ''
  customerLocation.value = ''
  includedDebtIds.value = []
  deliveryPrice.value = 0
  deliveryPhone.value = ''
  deliveryLocation.value = ''
  needsDelivery.value = false
  depositInput.value = 0
  paymentMethod.value = 'Cash'
  step.value = 'cart'
}

function goNext() {
  if (!cart.value.length) return
  void store.fetchList('customers')
  void store.fetchList('customerDebts')
  void store.fetchList('sales')
  step.value = 'checkout'
}

function goBack() {
  step.value = 'cart'
}

watch(includedDebtIds, () => {
  depositInput.value = selectedDeposit.value
}, { deep: true })

watch(customerId, (id) => {
  includedDebtIds.value = []
  if (!id) {
    customerName.value = ''
    customerPhone.value = ''
    customerLocation.value = ''
    return
  }
  const row = store.get('customers', String(id))
  customerName.value = String(row?.name || '')
  customerPhone.value = String(row?.phone || '')
  customerLocation.value = String(row?.location || row?.address || '')
})

watch(paymentMethod, (method) => {
  if (method === 'Credit') paidInput.value = 0
  else paidInput.value = undefined
})

/** Walk-in customers cannot take debt (spec §5.11): switching to Credit
 *  without a registered customer is blocked with a hint. */
watch(isCredit, (credit) => {
  if (credit && !customerId.value) {
    toast.add({ title: t('app.pos.creditRequiresCustomer'), color: 'warning' })
    paymentMethod.value = 'Cash'
  }
})

/* ------------------------- Invoice print size + currency chooser ------------------------- */

/** Paper-size + print-currency chooser opened after a successful Submit (A4 default). */
const printSizeOpen = ref(false)
let printSizeResolver: ((choice: { size: PrintPaperSize, options: PrintCurrencyChoice } | null) => void) | null = null

/** Resolves with the chosen size + currency, or null when the cashier closes/cancels. */
function choosePrintSize(): Promise<{ size: PrintPaperSize, options: PrintCurrencyChoice } | null> {
  return new Promise((resolve) => {
    printSizeResolver = resolve
    printSizeOpen.value = true
  })
}

function onPrintSizeConfirm(size: PrintPaperSize, options: PrintCurrencyChoice) {
  printSizeOpen.value = false
  printSizeResolver?.({ size, options })
  printSizeResolver = null
}

watch(printSizeOpen, (open) => {
  if (!open && printSizeResolver) {
    const resolve = printSizeResolver
    printSizeResolver = null
    resolve(null) // closed/cancelled — sale already succeeded, skip print
  }
})

async function completeSale() {
  if (!cart.value.length || !canOperate.value || completing.value) return
  if (outstandingAmount.value > 0 && !customerId.value) {
    toast.add({ title: t('app.pos.creditRequiresCustomer'), color: 'warning' })
    return
  }
  if (saleCurrency.value === 'KHR' && saleRate.value <= 0) {
    toast.add({ title: t('app.pos.exchangeRateRequired'), color: 'warning' })
    return
  }
  completing.value = true
  try {
    const snapshot = cart.value.map(line => ({ ...line }))
    const sale = await posCommands.completeSale({
      customerId: customerId.value ? String(customerId.value) : null,
      customerName: customerName.value || null,
      items: cart.value.map(line => ({
        productId: line.productId,
        quantity: line.quantity,
        // Line prices are sent in the document currency (KHR sale uses rate).
        unitPrice: docFromUsd(line.unitPrice),
        discountPercent: line.discountPercent,
        uomId: line.uomId || undefined,
        uomSymbol: line.uom || undefined,
        factorToBase: line.factorToBase || 1,
      })),
      paymentMethod: paymentMethod.value,
      paidAmount: paidAmount.value,
      discount: docFromUsd(discountTotal.value),
      deliveryPrice: appliedDeliveryPrice.value,
      deposit: depositInput.value,
      includedDebtIds: includedDebtIds.value,
      currency: saleCurrency.value,
      exchangeRate: saleRate.value,
    })
    lastSaleNo.value = String(sale.invoiceNo || sale.saleNo || '')
    lastSaleId.value = String(sale.id || '')
    const shouldOpenDelivery = needsDelivery.value && canCreateDelivery.value
    // Invoice payload comes from the sale receipt contract (mock: derived
    // from the stored sale; HTTP: GET /pos/sales/{id}/receipt). Falls back to
    // the cart snapshot if the receipt cannot be read. No invoice.pdf call.
    let printLines: SaleInvoicePrintInput['lines'] = snapshot
    try {
      const receipt = await posCommands.getSaleReceipt(lastSaleId.value)
      printLines = receipt.items.map(item => ({
        name: item.name,
        uom: item.uom,
        quantity: item.quantity,
        unitPrice: item.unitPrice,
        discountPercent: item.unitPrice > 0 && item.quantity > 0
          ? Math.round((item.discount / (item.unitPrice * item.quantity)) * 10000) / 100
          : 0,
      }))
    }
    catch {
      // Keep the snapshot lines — printing must not fail because of the receipt.
    }
    const printInput: SaleInvoicePrintInput = {
      shopName: shopName.value,
      invoiceNo: lastSaleNo.value,
      dateLabel: dateLabel.value,
      customerName: customerName.value || String(sale.customer || t('app.pos.walkIn')),
      cashier: cashierName.value,
      currency: currency.value,
      lines: printLines,
      deliveryPrice: appliedDeliveryPrice.value,
      previousDebtAmount: previousDebtTotal.value,
      depositAmount: paidAmount.value,
      outstandingAmount: totalOutstanding.value,
    }
    toast.add({
      title: `${t('app.pos.saleCompleted')} · ${lastSaleNo.value}`,
      color: 'success',
    })
    cart.value = []
    paidInput.value = undefined
    customerId.value = undefined
    customerName.value = ''
    customerPhone.value = ''
    customerLocation.value = ''
    includedDebtIds.value = []
    deliveryPrice.value = 0
    deliveryPhone.value = ''
    deliveryLocation.value = ''
    needsDelivery.value = false
    depositInput.value = 0
    paymentMethod.value = 'Cash'
    saleCurrency.value = 'USD'
    exchangeRateInput.value = undefined
    step.value = 'cart'
    void store.fetchList('products')
    void store.fetchList('sales')
    void store.fetchList('customers')
    void store.fetchList('customerDebts')
    void store.fetchList('stockMovements')
    // Ask which paper size + print currency to use; closing skips print.
    const printChoice = await choosePrintSize()
    if (printChoice) await printSaleInvoice(printInput, printChoice.size, printChoice.options)
    if (shouldOpenDelivery) {
      await navigateTo(`/delivery-notes/new?saleId=${lastSaleId.value}&phone=${encodeURIComponent(deliveryPhone.value)}&location=${encodeURIComponent(deliveryLocation.value)}`)
    }
  }
  catch (error: unknown) {
    toast.add({
      title: t('app.pos.saleFailed'),
      description: error instanceof Error ? error.message : String(error),
      color: 'error',
    })
  }
  finally {
    completing.value = false
  }
}

</script>

<template>
  <div class="flex h-full min-h-0 flex-1 flex-col overflow-hidden">
    <LayoutAppHeaderPageActions
      v-if="step === 'cart'"
      :can-create="false"
      :can-export="false"
      :show-more-actions="false"
      @refresh="() => { void store.fetchList('products') }"
    >
      <UButton
        color="primary"
        icon="i-lucide-arrow-right"
        trailing
        class="rounded-sm"
        :disabled="!canOperate || !cart.length"
        :label="t('app.pos.next')"
        @click="goNext"
      />
    </LayoutAppHeaderPageActions>

    <div
      v-if="step === 'cart'"
      class="flex h-full min-h-0 flex-1 flex-col gap-3 overflow-hidden p-3 lg:flex-row"
    >
      <PosProductBrowser
        v-model:search="search"
        v-model:category-id="categoryId"
        :products="products"
        :categories="categoryOptions"
        :currency="currency"
        :disabled="!canOperate"
        @add="addProduct"
        @search-enter="onSearchEnter"
      />
      <PosCartPanel
        :cart="cart"
        :currency="currency"
        :sale-currency="saleCurrency"
        :sale-rate="saleRate"
        :disabled="!canOperate"
        @change-qty="changeQty"
        @change-uom="changeUom"
        @update-price="updatePrice"
        @update-discount="updateDiscount"
        @update-sale-currency="onSaleCurrencyChange"
        @remove="removeLine"
        @clear="clearCart"
      />
    </div>

    <PosCheckoutPanel
      v-else
      v-model:customer-id="customerId"
      v-model:customer-name="customerName"
      v-model:payment-method="paymentMethod"
      v-model:paid-input="paidInput"
      v-model:delivery-price="deliveryPrice"
      v-model:delivery-phone="deliveryPhone"
      v-model:delivery-location="deliveryLocation"
      v-model:needs-delivery="needsDelivery"
      v-model:deposit-input="depositInput"
      v-model:included-debt-ids="includedDebtIds"
      v-model:exchange-rate="exchangeRateInput"
      :customer-phone="customerPhone"
      :customer-location="customerLocation"
      :sale-currency="saleCurrency"
      :cart="cart"
      :currency="currency"
      :sale-rate="saleRate"
      :debts="openDebts"
      :customer-options="customerOptions"
      :can-operate="canOperate"
      :completing="completing"
      @update:sale-currency="onSaleCurrencyChange"
      @back="goBack"
      @complete="completeSale"
    />

    <PosPrintSizeDialog
      v-model:open="printSizeOpen"
      :document-currency="currency"
      @confirm="onPrintSizeConfirm"
    />

    <!-- Shared KHR exchange-rate dialog: opened by any USD/KHR price toggle. -->
    <CommonAppExchangeRateDialog
      v-model:open="exchangeRateDialogOpen"
      @confirm="confirmSaleExchangeRate"
    />
  </div>
</template>
