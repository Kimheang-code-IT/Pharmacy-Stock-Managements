<script setup lang="ts">
import * as z from 'zod'
import type { FormSubmitEvent } from '@nuxt/ui'
import { useAuth } from '~/composables/auth/useAuth'
import { usePageSeo } from '~/composables/usePageSeo'

/**
 * Initial administrator setup. In mock mode this creates the local demo
 * session directly; the real backend allows this endpoint only once.
 */
definePageMeta({
  layout: 'auth',
})

const { t } = useI18n()
const router = useRouter()
const toast = useToast()
const { loginWithCredentials } = useAuth()
const submitting = ref(false)

usePageSeo({
  title: () => t('pages.auth.setupTitle'),
  description: () => t('pages.auth.setupDesc'),
  robots: 'index, nofollow',
})

const schema = z.object({
  shopName: z.string().min(1, { error: t('pages.auth.shopNameRequired') }),
  email: z.email({ error: t('pages.auth.emailRequired') }),
  password: z.string().min(6, { error: t('pages.auth.passwordRequired') }),
  passwordConfirmation: z.string().min(6, { error: t('pages.auth.passwordRequired') }),
}).refine(data => data.password === data.passwordConfirmation, {
  message: t('pages.auth.passwordMismatch'),
  path: ['passwordConfirmation'],
})

type Schema = z.output<typeof schema>

const state = reactive({
  shopName: '',
  email: '',
  password: '',
  passwordConfirmation: '',
})

async function onSubmit(payload: FormSubmitEvent<Schema>) {
  if (submitting.value) return
  submitting.value = true
  try {
    const result = await loginWithCredentials(payload.data.email, payload.data.password)
    const user = result.data?.user
    if (!user) throw new Error('Setup failed')
    toast.add({ title: t('pages.auth.setupDone'), color: 'success' })
    await router.replace('/')
  }
  catch {
    toast.add({
      title: t('pages.auth.setupFailed'),
      description: t('pages.auth.setupFailedDesc'),
      color: 'error',
    })
  }
  finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="w-full max-w-md">
    <UForm
      :schema="schema"
      :state="state"
      class="space-y-4"
      @submit="onSubmit"
    >
      <div class="text-center">
        <LayoutAppBrandLogo img-class="mx-auto size-24 object-contain" />
        <h1 class="mt-3 text-xl font-semibold text-highlighted">{{ t('core.brand.name') }}</h1>
        <p class="mt-1 text-sm font-medium text-highlighted">{{ t('pages.auth.setupTitle') }}</p>
        <p class="mt-1 text-sm text-muted">{{ t('pages.auth.setupDesc') }}</p>
      </div>

      <UFormField :label="t('pages.auth.shopName')" name="shopName" required>
        <UInput
name="shopName"
type="text"
size="lg"
class="w-full"
:placeholder="t('pages.auth.shopNamePlaceholder')" />
      </UFormField>
      <UFormField :label="t('pages.auth.email')" name="email" required>
        <UInput
name="email"
type="email"
size="lg"
class="w-full"
placeholder="admin@stockpos.local" />
      </UFormField>
      <UFormField :label="t('pages.auth.password')" name="password" required>
        <UInput
name="password"
type="password"
size="lg"
class="w-full" />
      </UFormField>
      <UFormField :label="t('pages.auth.passwordConfirm')" name="passwordConfirmation" required>
        <UInput
name="passwordConfirmation"
type="password"
size="lg"
class="w-full" />
      </UFormField>

      <UButton
        type="submit"
        block
        size="lg"
        :loading="submitting"
        :label="t('pages.auth.setupBtn')"
      />

      <p class="text-center text-sm text-muted">
        <ULink to="/auth/login" class="underline">{{ t('pages.auth.backToLogin') }}</ULink>
      </p>
    </UForm>
  </div>
</template>