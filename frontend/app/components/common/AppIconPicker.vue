<script setup lang="ts">
const COMMON_ICONS = [
  'i-lucide-file-text',
  'i-lucide-inbox',
  'i-lucide-send',
  'i-lucide-folder',
  'i-lucide-shapes',
  'i-lucide-list-tree',
  'i-lucide-files',
  'i-lucide-building-2',
  'i-lucide-users',
  'i-lucide-user',
  'i-lucide-calendar',
  'i-lucide-clipboard-list',
  'i-lucide-mail',
  'i-lucide-phone',
  'i-lucide-globe',
  'i-lucide-lock',
  'i-lucide-star',
  'i-lucide-flag',
  'i-lucide-tag',
  'i-lucide-bookmark',
  'i-lucide-briefcase',
  'i-lucide-check-circle',
  'i-lucide-alert-triangle',
  'i-lucide-settings',
]

const model = defineModel<string>({ default: '' })

const props = withDefaults(defineProps<{
  label?: string
  labelKey?: string
  help?: string
  icons?: string[]
  disabled?: boolean
}>(), {
  disabled: false,
})

const { t, te } = useI18n()
const open = ref(false)
const query = ref('')

const labelText = computed(() => {
  if (props.label) return props.label
  if (props.labelKey && te(props.labelKey)) return t(props.labelKey)
  return t('core.common.icon')
})

const iconList = computed(() => props.icons?.length ? props.icons : COMMON_ICONS)

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return iconList.value
  return iconList.value.filter(icon => icon.toLowerCase().includes(q))
})

function select(icon: string) {
  model.value = icon
  open.value = false
}

function clear() {
  model.value = ''
}
</script>

<template>
  <UFormField :label="labelText" :help="props.help || undefined">
    <div class="flex items-center gap-2">
      <UButton
        color="neutral"
        variant="outline"
        size="md"
        :disabled="disabled"
        class="min-w-40 justify-start"
        @click="open = true"
      >
        <UIcon v-if="model" :name="model" class="size-4" />
        <span class="truncate text-sm">{{ model || t('core.common.chooseIcon') }}</span>
      </UButton>
      <UButton
        v-if="model"
        icon="i-lucide-x"
        color="neutral"
        variant="ghost"
        size="sm"
        :disabled="disabled"
        :aria-label="t('core.common.clear')"
        @click="clear"
      />
    </div>

    <UModal v-model:open="open" :dismissible="false">
      <template #content>
        <UCard>
          <template #header>
            <div class="flex items-center justify-between gap-3">
              <h3 class="text-base font-semibold">
                {{ t('core.common.chooseIcon') }}
              </h3>
              <div class="flex items-center gap-2">
                <CommonAppLiveSearch
                  v-model="query"
                  :placeholder="t('core.common.search')"
                  class="max-w-56"
                  size="sm"
                />
                <UButton
                  icon="i-lucide-x"
                  color="primary"
                  variant="outline"
                  size="sm"
                  square
                  class="rounded-full"
                  :aria-label="t('actions.close')"
                  :title="t('actions.close')"
                  @click="open = false"
                />
              </div>
            </div>
          </template>

          <div class="grid max-h-80 grid-cols-6 gap-2 overflow-y-auto sm:grid-cols-8">
            <UButton
              v-for="icon in filtered"
              :key="icon"
              color="neutral"
              :variant="model === icon ? 'soft' : 'ghost'"
              square
              :aria-label="icon"
              @click="select(icon)"
            >
              <UIcon :name="icon" class="size-5" />
            </UButton>
          </div>
        </UCard>
      </template>
    </UModal>
  </UFormField>
</template>
