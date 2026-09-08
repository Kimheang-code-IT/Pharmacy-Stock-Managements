export function compactQuery(query: object | undefined): Record<string, unknown> | undefined {
  if (!query) return undefined

  const compacted = Object.fromEntries(
    Object.entries(query).filter(([, value]) => {
      if (value === null || value === undefined) return false
      if (typeof value === 'string') return value.trim().length > 0
      if (Array.isArray(value)) return value.length > 0
      return true
    })
  )

  return Object.keys(compacted).length ? compacted : undefined
}
