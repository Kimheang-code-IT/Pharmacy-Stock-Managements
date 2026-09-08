import { describe, expect, it } from 'vitest'
import { limitFilterSelects, matchesFilter, parseFilterQuery } from '../app/utils/filter/values'

describe('parseFilterQuery', () => {
  it('splits comma lists, arrays, and blanks', () => {
    expect(parseFilterQuery('')).toEqual([])
    expect(parseFilterQuery('Draft')).toEqual(['Draft'])
    expect(parseFilterQuery('Draft,Issued')).toEqual(['Draft', 'Issued'])
    expect(parseFilterQuery(['Draft', 'Issued', 'Draft'])).toEqual(['Draft', 'Issued'])
    expect(parseFilterQuery(['Draft,Sent', 'Accepted'])).toEqual(['Draft', 'Sent', 'Accepted'])
    expect(parseFilterQuery({ value: 'Issued' })).toEqual(['Issued'])
  })
})

describe('matchesFilter', () => {
  it('keeps every row when nothing is selected', () => {
    expect(matchesFilter('Draft', [])).toBe(true)
    expect(matchesFilter('Draft', '')).toBe(true)
  })

  it('keeps rows whose value is in the selected list', () => {
    expect(matchesFilter('Draft', ['Draft', 'Issued'])).toBe(true)
    expect(matchesFilter('Cancelled', ['Draft', 'Issued'])).toBe(false)
    expect(matchesFilter('Issued', 'Issued')).toBe(true)
  })
})

describe('limitFilterSelects', () => {
  const filters = ['customer', 'branch', 'direction', 'status']
  const isStatus = (item: string) => item === 'status'

  it('removes status from a full four-select toolbar even without a date picker', () => {
    expect(limitFilterSelects(filters, false, isStatus)).toEqual(['customer', 'branch', 'direction'])
  })
  it('caps at three and drops status first when a date picker is present', () => {
    expect(limitFilterSelects(filters, true, isStatus)).toEqual(['customer', 'branch', 'direction'])
  })

  it('keeps status when the toolbar is under the cap', () => {
    expect(limitFilterSelects(['branch', 'status'], false, isStatus)).toEqual(['branch', 'status'])
    expect(limitFilterSelects(['branch', 'status'], true, isStatus)).toEqual(['branch', 'status'])
  })

  it('keeps status when dropping it would leave too few selects', () => {
    const manyStatus = ['status', 'customer', 'branch', 'direction', 'currency']
    expect(limitFilterSelects(manyStatus, true, isStatus)).toEqual(['customer', 'branch', 'direction'])
  })
})
