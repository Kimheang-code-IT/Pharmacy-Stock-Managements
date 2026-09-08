export const SAFE_RASTER_IMAGE_TYPES = [
  'image/png',
  'image/jpeg',
  'image/webp',
  'image/gif',
] as const

export const SAFE_RASTER_IMAGE_ACCEPT = SAFE_RASTER_IMAGE_TYPES.join(',')

export const DEFAULT_UPLOAD_TYPES = [
  'application/pdf',
  'image/png',
  'image/jpeg',
  'image/webp',
  '.doc',
  '.docx',
  '.xls',
  '.xlsx',
  '.zip',
] as const

export function isSafeRasterImage(file: Pick<File, 'type' | 'size'>, maxSizeMb: number): boolean {
  return SAFE_RASTER_IMAGE_TYPES.includes(file.type as (typeof SAFE_RASTER_IMAGE_TYPES)[number])
    && file.size <= maxSizeMb * 1024 * 1024
}

export function fileMatchesAllowedTypes(file: Pick<File, 'name' | 'type'>, allowed: readonly string[]): boolean {
  const name = file.name.toLowerCase()
  const mime = file.type.toLowerCase()
  return allowed.some((rule) => {
    const normalized = rule.toLowerCase().trim()
    if (normalized.startsWith('.')) return name.endsWith(normalized)
    if (normalized.endsWith('/*')) return mime.startsWith(normalized.slice(0, -1))
    return mime === normalized
  })
}
