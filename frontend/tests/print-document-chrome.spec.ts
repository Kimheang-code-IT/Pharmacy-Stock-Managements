import { describe, expect, it } from 'vitest'
import {
  printDocColgroup,
  printDocFillerRow,
  printDocHeadRow,
  printDocMeta,
  printDocNote,
  printDocSignatures,
  printDocTitle,
} from '../app/utils/print/document'

describe('reusable print-document chrome (shared by invoice + delivery note)', () => {
  it('escapes the underlined document title (never the shop name)', () => {
    const html = printDocTitle('ប័ណ្ណដឹកជញ្ជូន / DELIVERY NOTE <b>')
    expect(html).toContain('<p class="title">')
    expect(html).toContain('&lt;b&gt;')
    expect(html).not.toContain('<b>')
  })

  it('renders bold left/right meta stacks with escaped values', () => {
    const html = printDocMeta(
      [{ label: 'លេខប័ណ្ណ / No', value: 'DN-000001' }, { label: 'Phone', value: '<012>' }],
      [{ label: 'Date', value: '2026-09-10' }],
    )
    expect(html).toContain('<div class="meta">')
    expect(html).toContain('DN-000001')
    expect(html).toContain('&lt;012&gt;')
    expect(html).toContain('<div class="right">')
  })

  it('builds stacked bilingual header rows with num alignment', () => {
    const html = printDocHeadRow([
      { label: 'ល.រ', sub: 'N°' },
      { label: 'បញ្ជូន', sub: 'To Deliver', align: 'num' },
    ])
    expect(html).toContain('<th>ល.រ<span>N°</span></th>')
    expect(html).toContain('<th class="num">')
    expect(html).toContain('<span>To Deliver</span>')
  })

  it('emits colgroup widths and filler rows for the page-height budget', () => {
    const colgroup = printDocColgroup(['5%', '33%'])
    expect(colgroup).toContain('<col style="width: 5%">')
    const filler = printDocFillerRow(5)
    expect((filler.match(/<tr class="empty">/g) || []).length).toBe(1)
    expect((filler.match(/<td>/g) || []).length).toBe(5)
  })

  it('omits an empty note and prints a filled one', () => {
    expect(printDocNote('Note', '   ')).toBe('')
    expect(printDocNote('កំណត់សម្គាល់ / Note', 'Call first')).toContain('Call first')
  })

  it('renders one signature block per label with a rule line', () => {
    const html = printDocSignatures(['អ្នកទទួល / Receiver', 'អ្នកដឹកជញ្ជូន / Delivery staff'])
    expect((html.match(/<div class="sign">/g) || []).length).toBe(2)
    expect((html.match(/<div class="line"><\/div>/g) || []).length).toBe(2)
  })
})