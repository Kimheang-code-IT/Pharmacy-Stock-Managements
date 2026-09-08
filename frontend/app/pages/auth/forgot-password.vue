<script setup lang="ts">
import * as z from 'zod'
import type { FormSubmitEvent } from '@nuxt/ui'
import { useAuth } from '~/composables/auth/useAuth'
import { usePageSeo } from '~/composables/usePageSeo'
import { startPasswordReset } from '~/utils/auth/password-reset'

definePageMeta({
  layout: 'auth',
})

const { t } = useI18n()
const router = useRouter()
const toast = useToast()
const { requestPasswordReset } = useAuth()
const submitting = ref(false)

usePageSeo({
  title: () => t('pages.forgetPassword.title'),
  description: () => t('pages.forgetPassword.desc'),
  robots: 'noindex, nofollow',
})

const schema = computed(() => z.object({
  email: z.email({ error: t('pages.auth.emailRequired') }),
}))

const fields = computed(() => [
  {
    name: 'email',
    type: 'email' as const,
    size: 'lg' as const,
    label: t('pages.auth.email'),
    placeholder: t('pages.auth.emailPlaceholder'),
    required: true,
    autocomplete: 'email',
  },
])

type Schema = { email: string }

async function onSubmit(payload: FormSubmitEvent<Schema>) {
  if (submitting.value) return
  submitting.value = true
  try {
    const email = payload.data.email.trim()
    await requestPasswordReset(email)
    startPasswordReset(email)
    toast.add({
      title: t('pages.forgetPassword.sentTitle'),
      description: t('pages.forgetPassword.sentDesc', { email }),
      color: 'success',
    })
    await router.push('/auth/verify-code')
  }
  finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="flex flex-col items-center justify-center">
    <UAuthForm
      :schema="schema"
      :title="t('pages.forgetPassword.title')"
      icon="i-lucide-send"
      :fields="fields"
      :loading="submitting"
      :submit="{
        label: t('pages.forgetPassword.submitBtn'),
        class: 'w-full h-10! text-base font-normal',
        loading: submitting,
      }"
      @submit="onSubmit"
    >
      <template #leading>
        <div class="mx-auto flex size-28 items-center justify-center overflow-hidden">
          <LayoutAppBrandLogo img-class="size-28 object-contain" />
        </div>
      </template>

      <template #footer>
        <div class="space-y-2 text-center">
          <UButton
            variant="link"
            size="sm"
            to="/auth/login"
            class="text-muted-foreground underline"
          >
            <UIcon name="i-lucide-arrow-left" class="mr-1" />
            {{ t('pages.forgetPassword.backToLogin') }}
          </UButton>
          <div>
            <span class="text-sm font-normal text-muted">{{ $t('settings.aboutCopyright') }}</span>
          </div>
        </div>
      </template>
    </UAuthForm>
  </div>
</template>
