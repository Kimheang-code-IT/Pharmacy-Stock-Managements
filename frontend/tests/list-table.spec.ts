import { describe, expect, it } from 'vitest'
import { listTablePageSummary, listTableSelectedIds, listTableVirtualize } from '../app/utils/table/list-table'

const t = (key: string, values?: Record<string, unknown>) => {
  if (key === 'app.ui.ofZero') return '0 of 0'
  if (key === 'app.ui.of') return `${values?.shown} of ${values?.total}`
  return key
}

describe('list table helpers', () => {
  it('summarizes the visible page', () => {
    expect(listTablePageSummary(t, 0, { pageIndex: 0, pageSize: 20 })).toBe('0 of 0')
    expect(listTablePageSummary(t, 6, { pageIndex: 0, pageSize: 20 })).toBe('6 of 6')
    expect(listTablePageSummary(t, 45, { pageIndex: 1, pageSize: 20 })).toBe('20 of 45')
  })

  it('lists selected row ids', () => {
    expect(listTableSelectedIds({ a: true, b: false, c: true })).toEqual(['a', 'c'])
  })

  it('virtualizes only large lists', () => {
    expect(listTableVirtualize(10, 20)).toBe(false)
    expect(listTableVirtualize(200, 20)).toMatchObject({ estimateSize: 48, overscan: 12 })
  })
})
