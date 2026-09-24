<script setup lang="ts">
import * as z from 'zod'
import type { FormSubmitEvent } from '@nuxt/ui'
import { useAuth } from '~/composables/auth/useAuth'
import { usePageSeo } from '~/composables/usePageSeo'

/**
 * Initial administrator setup (`POST /auth/setup`); the backend allows this
 * endpoint only once.
 */
definePageMeta({
  layout: 'auth',
})

const { t } = useI18n()
const router = useRouter()
const toast = useToast()
const auth = useAuthStore()
const { setupAdministrator } = useAuth()
const submitting = ref(false)

usePageSeo({
  title: () => t('pages.auth.setupTitle'),
  description: () => t('pages.auth.setupDesc'),
  robots: 'index, nofollow',
})

const schema = z.object({
  email: z.email({ error: t('pages.auth.emailRequired') }),
  password: z.string().min(8, { error: t('pages.auth.passwordRequired') }),
  passwordConfirmation: z.string().min(8, { error: t('pages.auth.passwordRequired') }),
}).refine(data => data.password === data.passwordConfirmation, {
  message: t('pages.auth.passwordMismatch'),
  path: ['passwordConfirmation'],
})

type Schema = z.output<typeof schema>

const state = reactive({
  email: '',
  password: '',
  passwordConfirmation: '',
})

const showPassword = ref(false)
const showPasswordConfirmation = ref(false)

async function onSubmit(payload: FormSubmitEvent<Schema>) {
  if (submitting.value) return
  submitting.value = true
  try {
    const email = payload.data.email.trim()
    const fullName = email.split('@')[0]?.trim() || 'Administrator'
    const result = await setupAdministrator({
      fullName,
      email,
      password: payload.data.password,
      passwordConfirmation: payload.data.passwordConfirmation,
    })
    const user = result.data?.user
    if (!user) throw new Error('Setup failed')
    auth.login(user)
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
      </div>

      <UFormField :label="t('pages.auth.email')" name="email" required>
        <UInput
v-model="state.email"
name="email"
type="email"
size="lg"
class="w-full"
placeholder="admin@stockpos.local" />
      </UFormField>
      <UFormField :label="t('pages.auth.password')" name="password" required>
        <UInput
v-model="state.password"
name="password"
:type="showPassword ? 'text' : 'password'"
size="lg"
class="w-full"
:placeholder="t('pages.auth.passwordPlaceholder')"
:ui="{ trailing: 'pe-1' }">
          <template #trailing>
            <UButton
:icon="showPassword ? 'i-lucide-eye-off' : 'i-lucide-eye'"
color="neutral"
variant="link"
size="sm"
:aria-label="showPassword ? t('core.common.hideSecret') : t('core.common.showSecret')"
@click="showPassword = !showPassword" />
          </template>
        </UInput>
      </UFormField>
      <UFormField :label="t('pages.auth.passwordConfirm')" name="passwordConfirmation" required>
        <UInput
v-model="state.passwordConfirmation"
name="passwordConfirmation"
:type="showPasswordConfirmation ? 'text' : 'password'"
size="lg"
class="w-full"
:placeholder="t('pages.auth.passwordConfirmPlaceholder')"
:ui="{ trailing: 'pe-1' }">
          <template #trailing>
            <UButton
:icon="showPasswordConfirmation ? 'i-lucide-eye-off' : 'i-lucide-eye'"
color="neutral"
variant="link"
size="sm"
:aria-label="showPasswordConfirmation ? t('core.common.hideSecret') : t('core.common.showSecret')"
@click="showPasswordConfirmation = !showPasswordConfirmation" />
          </template>
        </UInput>
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