/**
 * Cmd+K global search: keyword / semantic modes, Ask AI on demand, source links.
 */
import type { CommandPaletteItem, CommandPaletteGroup, NavigationMenuItem } from '@nuxt/ui'
import type { SearchHit, SearchMode } from '~/types/stock-pos/search'
import { ensureSearchIndexSeeded } from '~/utils/search/seed-index'
import { useMenu } from '~/composables/layout/useMenu'
import { useSearch } from '~/composables/search/useSearch'

export function useGlobalSearch() {
  const { t } = useI18n()
  const router = useRouter()
  const { links, close: closeSidebar } = useMenu()
  const { askAi, searchKeyword, searchSemantic } = useSearch()

  const open = ref(false)
  const searchTerm = ref('')
  const mode = ref<SearchMode>('keyword')
  const loading = ref(false)
  const asking = ref(false)
  const hits = ref<SearchHit[]>([])
  const aiAnswer = ref<string | null>(null)
  const aiCitations = ref<SearchHit[]>([])

  // The connected backend implements keyword search only. Hide Ask AI and the
  // semantic mode instead of labelling SQL keyword search as semantic AI.
  const isHttpMode = useRuntimeConfig().public.useMockData === false

  ensureSearchIndexSeeded()

  const navItems = computed<CommandPaletteItem[]>(() => {
    const items: CommandPaletteItem[] = []
    const navLinks = links.value?.[0] || []

    const pushLink = (label: string, to: string, icon?: string) => {
      items.push({
        id: `nav:${to}`,
        label,
        icon: icon || 'i-lucide-file',
        to,
        onSelect: () => {
          closeSidebar()
          open.value = false
        },
      })
    }

    for (const link of navLinks as NavigationMenuItem[]) {
      if (link.children?.length) {
        for (const child of link.children) {
          if (child.to) pushLink(String(child.label), String(child.to), child.icon || link.icon)
        }
      }
      else if (link.to) {
        pushLink(String(link.label), String(link.to), link.icon)
      }
    }

    // `useMenu` already applies the canonical permission keys.
    return items
  })

  async function runSearch(q: string) {
    const query = q.trim()
    aiAnswer.value = null
    aiCitations.value = []
    if (!query) {
      hits.value = []
      loading.value = false
      return
    }
    loading.value = true
    try {
      hits.value = mode.value === 'semantic'
        ? await searchSemantic(query, { limit: 12 })
        : await searchKeyword(query, { limit: 12 })
    }
    catch {
      hits.value = []
    }
    finally {
      loading.value = false
    }
  }

  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  watch([searchTerm, mode], ([q]) => {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => runSearch(String(q || '')), 120)
  })

  watch(open, (isOpen) => {
    if (isOpen) ensureSearchIndexSeeded()
    else {
      aiAnswer.value = null
      aiCitations.value = []
    }
  })

  async function onAskAi() {
    const q = searchTerm.value.trim()
    if (!q || asking.value) return
    asking.value = true
    try {
      const res = await askAi(q, hits.value)
      aiAnswer.value = res.answer
      aiCitations.value = res.citations
    }
    finally {
      asking.value = false
    }
  }

  function setMode(next: SearchMode) {
    mode.value = next
  }

  const resultItems = computed<CommandPaletteItem[]>(() =>
    hits.value.map(hit => ({
      id: hit.id,
      label: hit.title,
      description: `${hit.sourceLabel} · ${hit.snippet}`,
      icon: hit.entityType === 'file' || hit.entityType === 'attachment'
        ? 'i-lucide-paperclip'
        : hit.entityType === 'user'
          ? 'i-lucide-user'
          : 'i-lucide-file-text',
      to: hit.url,
      onSelect: () => {
        closeSidebar()
        open.value = false
      },
    })),
  )

  const askAiItems = computed<CommandPaletteItem[]>(() => {
    if (isHttpMode || !searchTerm.value.trim()) return []
    return [{
      id: 'action:ask-ai',
      label: asking.value ? t('core.search.asking') : t('core.search.askAi'),
      description: t('core.search.askAiHint'),
      icon: 'i-lucide-sparkles',
      disabled: asking.value || loading.value,
      onSelect: async (e: Event) => {
        e.preventDefault()
        await onAskAi()
      },
    }]
  })

  const citationItems = computed<CommandPaletteItem[]>(() =>
    aiCitations.value.map(hit => ({
      id: `cite:${hit.id}`,
      label: hit.title,
      description: `${t('core.search.source')}: ${hit.sourceLabel} · ${hit.url}`,
      icon: 'i-lucide-link',
      to: hit.url,
      onSelect: () => {
        closeSidebar()
        open.value = false
      },
    })),
  )

  const groups = computed<CommandPaletteGroup<CommandPaletteItem>[]>(() => {
    const out: CommandPaletteGroup<CommandPaletteItem>[] = []

    if (askAiItems.value.length) {
      out.push({
        id: 'ask-ai',
        label: t('core.search.askAiGroup'),
        ignoreFilter: true,
        items: askAiItems.value,
      })
    }

    if (aiAnswer.value) {
      out.push({
        id: 'ai-answer',
        label: t('core.search.aiAnswer'),
        ignoreFilter: true,
        items: [{
          id: 'ai-answer-body',
          label: aiAnswer.value.split('\n')[0] || t('core.search.aiAnswer'),
          description: aiAnswer.value,
          icon: 'i-lucide-bot',
          disabled: true,
        }],
      })
      if (citationItems.value.length) {
        out.push({
          id: 'ai-sources',
          label: t('core.search.sources'),
          ignoreFilter: true,
          items: citationItems.value,
        })
      }
    }

    if (resultItems.value.length) {
      out.push({
        id: 'records-files',
        label: t('core.search.recordsAndFiles'),
        ignoreFilter: true,
        items: resultItems.value,
      })
    }

    out.push({
      id: 'navigation',
      label: t('common.pages'),
      items: navItems.value,
    })

    return out
  })

  const placeholder = computed(() =>
    mode.value === 'semantic'
      ? t('core.search.placeholderSemantic')
      : t('core.search.placeholderKeyword'),
  )

  return {
    open,
    searchTerm,
    mode,
    setMode,
    loading,
    asking,
    groups,
    placeholder,
    onAskAi,
    isHttpMode,
    router,
  }
}

