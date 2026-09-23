import { readFileSync, readdirSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { allFrontendPermissionCodes } from '../app/utils/role/permissions'
import { PAGE_PERMISSIONS } from '../app/utils/role/page-permissions'

/**
 * Guards the RBAC contract: every frontend permission ID (page meta, module
 * config, role matrix mirror) must be a code the backend catalog emits in
 * `backend/app/core/permissions.py`. The backend is the authority.
 */

const here = dirname(fileURLToPath(import.meta.url))
const repoRoot = resolve(here, '../..')
const frontendRoot = resolve(here, '..')

/** Parse the backend PERMISSION_CATALOG into flat `module.action` codes. */
function backendPermissionCodes(): Set<string> {
  const source = readFileSync(join(repoRoot, 'backend/app/core/permissions.py'), 'utf8')
  const start = source.indexOf('PERMISSION_CATALOG')
  const end = source.indexOf('SERVICE_PERMISSIONS')
  const block = source.slice(start, end)
  const codes = new Set<string>(['ALL_PAGES'])
  const row = /"([a-z_]+)":\s*\(([^)]*)\)/g
  let match: RegExpExecArray | null
  while ((match = row.exec(block)) !== null) {
    const module = match[1]
    for (const action of match[2].matchAll(/"([^"]+)"/g)) codes.add(`${module}.${action[1]}`)
  }
  return codes
}

function walkVueFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = join(dir, entry.name)
    if (entry.isDirectory()) return walkVueFiles(full)
    return entry.name.endsWith('.vue') ? [full] : []
  })
}

function permissionLiterals(text: string): string[] {
  const values: string[] = []
  for (const match of text.matchAll(/permission:\s*'([^']+)'/g)) values.push(match[1])
  for (const match of text.matchAll(/createPermission:\s*'([^']+)'/g)) values.push(match[1])
  for (const block of text.matchAll(/actionPermissions:\s*\{([^}]*)\}/g)) {
    for (const value of block[1].matchAll(/'([^']+)'/g)) values.push(value[1])
  }
  return values
}

describe('frontend permission IDs match the backend catalog', () => {
  const valid = backendPermissionCodes()

  it('parses a non-trivial backend catalog', () => {
    expect(valid.size).toBeGreaterThan(30)
    expect(valid.has('stock.view')).toBe(true)
    expect(valid.has('product.update')).toBe(true)
    expect(valid.has('report.customer_debt')).toBe(true)
    expect(valid.has('supplier.debt.pay')).toBe(true)
  })

  it('role-matrix mirror contains only backend codes', () => {
    const unknown = allFrontendPermissionCodes().filter(code => !valid.has(code))
    expect(unknown, `unknown frontend codes: ${unknown.join(', ')}`).toEqual([])
  })

  it('page and module permission literals are backend codes', () => {
    const files = [
      ...walkVueFiles(join(frontendRoot, 'app/pages')),
      join(frontendRoot, 'app/config/stock-modules.ts'),
      join(frontendRoot, 'app/config/admin-modules.ts'),
      join(frontendRoot, 'app/config/delivery-modules.ts'),
    ]
    const unknown: string[] = []
    for (const file of files) {
      for (const code of permissionLiterals(readFileSync(file, 'utf8'))) {
        if (!valid.has(code)) unknown.push(`${code} (${file.replace(repoRoot, '')})`)
      }
    }
    expect(unknown, `unknown permission literals:\n${unknown.join('\n')}`).toEqual([])
  })

  it('exposes every POS action in the backend and the matrix mirror', () => {
    const posCodes = [
      'pos.access', 'pos.discount', 'pos.debt_sale', 'pos.print',
      'pos.sale_edit', 'pos.return', 'pos.refund',
    ]
    for (const code of posCodes) expect(valid.has(code), code).toBe(true)
    const frontend = new Set(allFrontendPermissionCodes())
    for (const code of ['pos.sale_edit', 'pos.return', 'pos.refund']) {
      expect(frontend.has(code), code).toBe(true)
    }
  })

  it('menu route guards are backend codes', () => {
    const codes = PAGE_PERMISSIONS.flatMap(page => [
      page.permission,
      ...page.actions.map(action => action.permission),
    ])
    expect(codes.length).toBeGreaterThan(15)
    const unknown = codes.filter(code => !valid.has(code))
    expect(unknown, `unknown route permissions: ${unknown.join(', ')}`).toEqual([])
  })
})
