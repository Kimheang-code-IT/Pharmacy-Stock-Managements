export interface CsvField {
  label: string
  value: string
}

/** Escape and download any row list as a CSV file (client side). */
export function downloadCsv(options: {
  filename: string
  fields: CsvField[]
  rows: Array<Record<string, unknown>>
}) {
  const { filename, fields, rows } = options
  const csv = [
    fields.map(field => field.label),
    ...rows.map(row => fields.map(field => String(row[field.value] ?? ''))),
  ]
    .map(line => line.map(cellValue => `"${cellValue.replaceAll('"', '""')}"`).join(','))
    .join('\n')
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}
