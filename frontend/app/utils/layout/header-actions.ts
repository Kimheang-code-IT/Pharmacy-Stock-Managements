export type HeaderListNavDirection = 'previous' | 'next' | null

/** Previous/next are locked while creating, at list ends, or while a nav request is in flight. */
export function headerListNavDisabled(options: {
  isCreate: boolean
  canNavigate: boolean
  loading: boolean
  direction: HeaderListNavDirection
}): boolean {
  return options.isCreate || !options.canNavigate || options.loading || Boolean(options.direction)
}
