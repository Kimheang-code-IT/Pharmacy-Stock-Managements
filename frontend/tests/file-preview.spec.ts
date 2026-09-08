import { describe, expect, it } from 'vitest'
import { filePreviewBlob, mimeFromFileName, mockPdfBytes } from '../app/utils/module/attachments'
import { safeExternalUrl, safeFilePreviewUrl } from '../app/utils/security/url'

describe('file preview', () => {
  it('maps common extensions to preview mime types', () => {
    expect(mimeFromFileName('BL-8821.pdf')).toBe('application/pdf')
    expect(mimeFromFileName('scan.PNG')).toBe('image/png')
    expect(mimeFromFileName('notes.txt')).toBe('text/plain')
    expect(mimeFromFileName('photo.jpg', 'image/jpeg')).toBe('image/jpeg')
  })

  it('builds a PDF the browser can open for seeded .pdf rows', async () => {
    const pdf = mockPdfBytes('BL-8821.pdf', 'Bill of lading')
    expect(pdf.startsWith('%PDF-1.4')).toBe(true)
    expect(pdf).toContain('%%EOF')
    const blob = filePreviewBlob({ fileName: 'BL-8821.pdf' })
    expect(blob?.type).toBe('application/pdf')
    expect((await blob!.text()).startsWith('%PDF-1.4')).toBe(true)
  })

  it('uses an SVG preview for image file names without bytes', () => {
    const blob = filePreviewBlob({ fileName: 'gate-photo.png' })
    expect(blob?.type).toBe('image/svg+xml')
  })

  it('rejects executable URL schemes and keeps http(s) plus blob', () => {
    expect(safeExternalUrl('javascript:alert(1)')).toBeNull()
    expect(safeFilePreviewUrl('javascript:alert(1)')).toBeNull()
    expect(safeFilePreviewUrl('https://files.example.com/bl.pdf')).toBe('https://files.example.com/bl.pdf')
    expect(safeFilePreviewUrl('blob:https://localhost/1234')).toBe('blob:https://localhost/1234')
  })
})
