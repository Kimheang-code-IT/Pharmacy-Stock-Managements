<script setup lang="ts">
import * as z from 'zod'
import type { FormSubmitEvent } from '@nuxt/ui'
import { useAuth } from '~/composables/auth/useAuth'
import { usePageSeo } from '~/composables/usePageSeo'
import {
  applyPasswordResetHandoff,
  clearPasswordResetSession,
  getPasswordResetSession,
} from '~/utils/auth/password-reset'

definePageMeta({
  layout: 'auth',
})

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const toast = useToast()
const { resetPasswordWithCode, exchangePasswordResetHandoff } = useAuth()
const submitting = ref(false)
const session = ref(getPasswordResetSession())
const handoffLoading = ref(false)

usePageSeo({
  title: () => t('pages.forgetPassword.resetTitle'),
  description: () => t('pages.forgetPassword.resetDesc'),
  robots: 'noindex, nofollow',
})

onMounted(async () => {
  const handoff = typeof route.query.handoff === 'string' ? route.query.handoff : ''
  if (handoff) {
    handoffLoading.value = true
    try {
      const result = await exchangePasswordResetHandoff(handoff)
      applyPasswordResetHandoff(result.data.email, result.data.resetToken)
      session.value = getPasswordResetSession()
      await router.replace({ path: route.path, query: {} })
    }
    catch {
      await router.replace('/auth/forgot-password')
    }
    finally {
      handoffLoading.value = false
    }
    return
  }

  session.value = getPasswordResetSession()
  if (!session.value?.email) {
    void router.replace('/auth/forgot-password')
    return
  }
  if (!session.value.verified || !session.value.resetToken) {
    void router.replace('/auth/verify-code')
  }
})

const schema = computed(() => z.object({
  password: z.string().min(6, { error: t('pages.forgetPassword.passwordMin') }),
  passwordConfirmation: z.string().min(6, { error: t('pages.forgetPassword.passwordMin') }),
}).refine(data => data.password === data.passwordConfirmation, {
  message: t('pages.forgetPassword.passwordMismatch'),
  path: ['passwordConfirmation'],
}))

const fields = computed(() => [
  {
    name: 'password',
    type: 'password' as const,
    size: 'lg' as const,
    label: t('pages.forgetPassword.newPassword'),
    placeholder: t('pages.forgetPassword.newPasswordPlaceholder'),
    required: true,
    autocomplete: 'new-password',
  },
  {
    name: 'passwordConfirmation',
    type: 'password' as const,
    size: 'lg' as const,
    label: t('pages.forgetPassword.confirmPassword'),
    placeholder: t('pages.forgetPassword.confirmPasswordPlaceholder'),
    required: true,
    autocomplete: 'new-password',
  },
])

type Schema = {
  password: string
  passwordConfirmation: string
}

async function onSubmit(payload: FormSubmitEvent<Schema>) {
  if (submitting.value || !session.value?.email || !session.value.resetToken) return
  submitting.value = true
  try {
    await resetPasswordWithCode({
      email: session.value.email,
      resetToken: session.value.resetToken,
      password: payload.data.password,
      passwordConfirmation: payload.data.passwordConfirmation,
    })
    clearPasswordResetSession()
    toast.add({
      title: t('pages.forgetPassword.resetSuccess'),
      description: t('pages.forgetPassword.resetSuccessDesc'),
      color: 'success',
    })
    await router.push('/auth/login')
  }
  catch {
    toast.add({
      title: t('pages.forgetPassword.resetFailed'),
      description: t('pages.forgetPassword.resetFailedDesc'),
      color: 'error',
    })
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
      :title="t('pages.forgetPassword.resetTitle')"
      icon="i-lucide-lock-keyhole"
      :fields="fields"
      :loading="submitting || handoffLoading"
      :submit="{
        label: t('pages.forgetPassword.resetSubmit'),
        class: 'w-full h-10! text-xl font-normal',
        loading: submitting,
      }"
      @submit="onSubmit"
    >
      <template #leading>
        <div class="mx-auto flex size-28 items-center justify-center overflow-hidden">
          <LayoutAppBrandLogo img-class="size-28 object-contain" />
        </div>
      </template>

      <template #description>
        <p class="text-center text-sm text-muted">
          {{ t('pages.forgetPassword.resetDesc', { email: session?.email || '…' }) }}
        </p>
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
