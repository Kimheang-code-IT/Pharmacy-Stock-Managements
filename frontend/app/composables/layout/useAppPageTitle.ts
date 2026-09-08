import type { MaybeRefOrGetter } from 'vue'
import { useAppHeader } from '~/composables/layout/useAppHeader'
import { usePageSeo } from '~/composables/usePageSeo'

/** Keep the shell title and document metadata synchronized for a page lifecycle. */
export function useAppPageTitle(title: MaybeRefOrGetter<string>) {
  const { setTitle, clear } = useAppHeader()
  const resolvedTitle = computed(() => toValue(title))

  onMounted(() => setTitle(resolvedTitle.value))
  watch(resolvedTitle, value => setTitle(value))
  onBeforeUnmount(clear)

  usePageSeo({ title: () => resolvedTitle.value })
}
