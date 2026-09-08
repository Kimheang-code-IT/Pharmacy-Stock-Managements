/**
 * Map mime type / filename to a Lucide icon + accent class for upload lists.
 */
export function fileTypeIcon(
  input?: string | { name?: string | null, type?: string | null, mimeType?: string | null } | null,
): { icon: string, class: string } {
  let mime = ''
  let name = ''

  if (typeof input === 'string') {
    if (input.includes('/')) mime = input
    else name = input
  }
  else if (input) {
    mime = String(input.mimeType || input.type || '')
    name = String(input.name || '')
  }

  const ext = name.includes('.') ? name.split('.').pop()!.toLowerCase() : ''

  if (mime.startsWith('image/') || ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp'].includes(ext)) {
    return { icon: 'i-lucide-image', class: 'text-sky-600 dark:text-sky-400' }
  }
  if (mime.startsWith('video/') || ['mp4', 'mov', 'webm', 'mkv'].includes(ext)) {
    return { icon: 'i-lucide-film', class: 'text-violet-600 dark:text-violet-400' }
  }
  if (mime.startsWith('audio/') || ['mp3', 'wav', 'ogg', 'm4a'].includes(ext)) {
    return { icon: 'i-lucide-music', class: 'text-fuchsia-600 dark:text-fuchsia-400' }
  }
  if (mime === 'application/pdf' || ext === 'pdf') {
    return { icon: 'i-lucide-file-text', class: 'text-red-600 dark:text-red-400' }
  }
  if (
    mime.includes('zip')
    || mime.includes('compressed')
    || ['zip', 'rar', '7z', 'tar', 'gz'].includes(ext)
  ) {
    return { icon: 'i-lucide-file-archive', class: 'text-amber-600 dark:text-amber-400' }
  }
  if (
    mime.includes('spreadsheet')
    || mime.includes('excel')
    || ['xls', 'xlsx', 'csv'].includes(ext)
  ) {
    return { icon: 'i-lucide-sheet', class: 'text-emerald-600 dark:text-emerald-400' }
  }
  if (
    mime.includes('presentation')
    || mime.includes('powerpoint')
    || ['ppt', 'pptx'].includes(ext)
  ) {
    return { icon: 'i-lucide-presentation', class: 'text-orange-600 dark:text-orange-400' }
  }
  if (
    mime.includes('word')
    || mime.includes('document')
    || ['doc', 'docx', 'rtf', 'odt', 'txt', 'md'].includes(ext)
  ) {
    return { icon: 'i-lucide-file-type', class: 'text-blue-600 dark:text-blue-400' }
  }

  return { icon: 'i-lucide-file', class: 'text-muted' }
}

