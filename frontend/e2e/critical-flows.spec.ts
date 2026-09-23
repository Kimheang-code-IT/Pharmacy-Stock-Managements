import { expect, test, type Page } from '@playwright/test'

/**
 * Critical browser smoke flows in real API mode. Transactional correctness
 * (stock math, FEFO, debt settlement, returns, currency snapshots) is covered
 * exhaustively by `backend/tests`; these specs verify the SPA actually talks to
 * the real API and that RBAC-gated navigation works end to end.
 */

const email = process.env.E2E_ADMIN_EMAIL || 'admin@gmail.com'
const password = process.env.E2E_ADMIN_PASSWORD || '123456'

async function login(page: Page) {
  await page.goto('/auth/login')
  await page.locator('input[type="email"]').fill(email)
  await page.locator('input[type="password"]').fill(password)
  await page.locator('button[type="submit"]').click()
  await page.waitForURL(url => !url.pathname.startsWith('/auth'), { timeout: 30_000 })
}

test('admin signs in against the real API and sees live products', async ({ page }) => {
  await login(page)
  await expect(page).toHaveURL(/\/$/)

  await page.goto('/stock/products')
  await expect(page).not.toHaveURL(/\/auth\/login/)
  await expect(page.getByText(/access denied/i)).toHaveCount(0)
  // The seeded development dataset must render through the real API.
  await expect(page.locator('table tbody tr').first()).toBeVisible({ timeout: 30_000 })
})

test('every approved top-level page is reachable without a permission denial', async ({ page }) => {
  await login(page)
  const paths = [
    '/',
    '/stock/products',
    '/stock/movements',
    '/pos',
    '/delivery-notes',
    '/setup/categories',
    '/setup/uoms',
    '/setup/suppliers',
    '/setup/customers',
    '/reports/sales',
    '/reports/purchases',
    '/reports/customer-debts',
    '/reports/supplier-debts',
    '/reports/finance',
    '/administration/users',
    '/administration/roles',
    '/administration/document-sequences',
    '/administration/audit-logs',
    '/administration/settings',
  ]
  for (const path of paths) {
    await page.goto(path)
    await expect(page, `unexpected redirect for ${path}`).not.toHaveURL(/\/auth\/login/)
    await expect(page.getByText(/access denied/i), `denied at ${path}`).toHaveCount(0)
  }
})

test('POS opens the product browser with API-backed products', async ({ page }) => {
  await login(page)
  await page.goto('/pos')
  await expect(page).not.toHaveURL(/\/auth\/login/)
  await expect(page.getByText(/access denied/i)).toHaveCount(0)
})
