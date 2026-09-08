import type { DropdownMenuItem } from '@nuxt/ui'
import { usePreferencesStore } from '~/stores/preferences'
import type { AppLocale } from '~/stores/preferences'
import type { AppFontSize } from '~/types/stock-pos/settings'
import { resolveUserAvatar } from '~/utils/auth/user-avatar'

const FONT_SIZE_OPTIONS: Array<{ value: AppFontSize, labelKey: string, icon: string }> = [
  { value: 'sm', labelKey: 'core.settings.fontSizeSm', icon: 'i-lucide-a-arrow-down' },
  { value: 'md', labelKey: 'core.settings.fontSizeMd', icon: 'i-lucide-type' },
  { value: 'lg', labelKey: 'core.settings.fontSizeLg', icon: 'i-lucide-a-arrow-up' },
  { value: 'xl', labelKey: 'core.settings.fontSizeXl', icon: 'i-lucide-fullscreen' },
]

export function useUserMenu() {
  const auth = useAuthStore()
  const preferences = usePreferencesStore()
  const colorMode = useColorMode()
  const i18n = useI18n()
  const { t } = i18n

  const aboutOpen = useState('user-menu-about-open', () => false)
  const profileOpen = useState('user-menu-profile-open', () => false)

  const user = computed(() => ({
    name: auth.user?.name || auth.user?.email || 'User',
    role: auth.user?.role || '',
    avatar: {
      src: resolveUserAvatar(auth.user),
      alt: auth.user?.name || 'User',
    },
  }))

  const items = computed<DropdownMenuItem[][]>(() => {
    const groups: DropdownMenuItem[][] = [
    [
      {
        label: user.value.name,
        avatar: user.value.avatar,
        onSelect(e: Event) {
          e.preventDefault()
          profileOpen.value = true
        },
      },
    ],
    [
      {
        label: t('settings.language'),
        icon: 'i-lucide-languages',
        children: (i18n.locales.value || [])
          .filter((loc: { code?: string }) => preferences.availableLocales.includes(loc.code as AppLocale))
          .map((loc: { name?: string, icon?: string, code?: string }) => ({
          label: loc.name,
          icon: loc.icon,
          type: 'checkbox',
          checked: i18n.locale.value === loc.code,
          onSelect: (e: Event) => {
            e.preventDefault()
            if (loc.code === 'en' || loc.code === 'km') {
              preferences.setLocale(loc.code as AppLocale)
            }
          },
        })),
      },
      {
        label: t('core.settings.fontSize'),
        icon: 'i-lucide-a-large-small',
        children: FONT_SIZE_OPTIONS.map(option => ({
          label: t(option.labelKey),
          icon: option.icon,
          type: 'checkbox',
          checked: preferences.fontSize === option.value,
          onSelect: (e: Event) => {
            e.preventDefault()
            preferences.setFontSize(option.value)
          },
        })),
      },
      {
        label: t('settings.about'),
        icon: 'i-lucide-info',
        onSelect(e: Event) {
          e.preventDefault()
          aboutOpen.value = true
        },
      },
      {
        label: t('settings.appearance'),
        icon: 'i-lucide-sun-moon',
        children: [
          {
            label: t('settings.light'),
            icon: 'i-lucide-sun',
            type: 'checkbox',
            checked: colorMode.value === 'light',
            onSelect(e: Event) {
              e.preventDefault()
              colorMode.preference = 'light'
            },
          },
          {
            label: t('settings.dark'),
            icon: 'i-lucide-moon',
            type: 'checkbox',
            checked: colorMode.value === 'dark',
            onUpdateChecked(checked: boolean) {
              if (checked) colorMode.preference = 'dark'
            },
            onSelect(e: Event) {
              e.preventDefault()
            },
          },
        ],
      },
    ],
    [
      {
        label: t('settings.logout'),
        icon: 'i-lucide-log-out',
        color: 'error',
        onSelect(e: Event) {
          e.preventDefault()
          auth.logout()
        },
      },
    ],
    ]
    return groups.filter(group => group.length > 0)
  })

  return {
    user,
    items,
    aboutOpen,
    profileOpen,
  }
}
