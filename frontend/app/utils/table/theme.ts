/** Shared Nuxt UI table chrome using semantic tokens for light and dark modes. */
export const appTableUi = {
  root: 'relative min-w-0 overflow-auto bg-default text-default',
  // border-separate is required: collapse prevents sticky headers from pinning.
  base: 'w-full min-w-max border-separate border-spacing-0',
  thead: 'relative z-10 bg-elevated text-highlighted backdrop-blur-none',
  tbody: [
    'bg-default text-default',
    '[&>tr:hover>td]:bg-muted',
    '[&>tr[data-selected=true]>td]:bg-primary/10',
    'dark:[&>tr[data-selected=true]>td]:bg-primary/15',
  ].join(' '),
  th: 'sticky top-0 z-10 border border-default bg-elevated px-3 py-2.5 text-left text-xs font-semibold text-highlighted whitespace-nowrap',
  td: 'border border-default bg-default px-3 py-2.5 align-middle text-default transition-colors',
  tr: 'cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary',
} as const

/** Denser rows and smaller cell type for document / line tables. */
export const appTableUiCompact = {
  ...appTableUi,
  th: 'sticky top-0 z-10 border border-default bg-elevated px-2 py-1 text-left text-[11px] font-semibold leading-tight text-highlighted whitespace-nowrap',
  td: 'border border-default bg-default px-2 py-1 align-middle text-xs leading-tight text-default transition-colors',
} as const

/** Full-height list tables: header stays put, only rows scroll. */
export const appTableFillUi = {
  ...appTableUi,
  root: 'relative h-full min-h-0 min-w-0 overflow-auto',
} as const

export const appTableUiReadonly = {
  ...appTableUi,
  tbody: 'bg-default text-default [&>tr:hover>td]:bg-muted',
  tr: '',
} as const

/** Document line tables: mid density — smaller than lists was too tight, this sits between. */
export const appTableUiLine = {
  ...appTableUiReadonly,
  th: 'sticky top-0 z-10 border border-default bg-elevated px-3 py-2 text-left text-xs font-semibold text-highlighted whitespace-nowrap',
  td: 'border border-default bg-default px-3 py-2 align-middle text-xs text-default transition-colors',
} as const

export const appTableUiCompactReadonly = {
  ...appTableUiCompact,
  tbody: 'bg-default text-default [&>tr:hover>td]:bg-muted',
  tr: '',
} as const

export const appTableFillUiReadonly = {
  ...appTableUiReadonly,
  root: 'relative h-full min-h-0 min-w-0 overflow-auto',
} as const

/** Centered checkbox column classes for list tables. */
export const appTableCheckboxMeta = {
  class: {
    th: 'sticky top-0 z-10 w-12 bg-elevated text-center align-middle',
    td: 'w-12 text-center align-middle',
  },
} as const

export const TABLE_VIRTUALIZE_AFTER = 80

