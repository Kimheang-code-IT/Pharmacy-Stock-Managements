<script setup lang="ts">
import * as z from 'zod'
import type { FormSubmitEvent } from '@nuxt/ui'
import { useAuth } from '~/composables/auth/useAuth'
import { useAuthStore } from '~/stores/auth'
import { resolveUserAvatar } from '~/utils/auth/user-avatar'

const open = defineModel<boolean>('open', { default: false })

const auth = useAuthStore()
const { changePassword, createTelegramLinkCode, removeProfileAvatar, updateProfileAvatar } = useAuth()
const { t } = useI18n()
const toast = useToast()

const submitting = ref(false)
const avatarSubmitting = ref(false)
const linkCodeLoading = ref(false)
const linkCode = ref<string | null>(null)
const avatarInputRef = ref<HTMLInputElement | null>(null)
const photoPreviewOpen = ref(false)

const telegramLinked = computed(() => Boolean(auth.user?.telegramLinked))

const profile = computed(() => {
  const user = auth.user
  return {
    name: user?.name || t('core.userProfile.unknownUser'),
    email: user?.email || '—',
    role: user?.role || t('core.userProfile.noRole'),
    avatar: {
      src: resolveUserAvatar(user),
      alt: user?.name || 'User',
    },
  }
})

const hasCustomAvatar = computed(() => Boolean(auth.user?.avatar))

const passwordSchema = computed(() => z.object({
  currentPassword: z.string().min(1, { error: t('core.userProfile.currentPasswordRequired') }),
  password: z.string().min(6, { error: t('pages.forgetPassword.passwordMin') }),
  passwordConfirmation: z.string().min(6, { error: t('pages.forgetPassword.passwordMin') }),
}).refine(data => data.password === data.passwordConfirmation, {
  message: t('pages.forgetPassword.passwordMismatch'),
  path: ['passwordConfirmation'],
}))

type PasswordSchema = z.infer<typeof passwordSchema.value>

const passwordState = reactive({
  currentPassword: '',
  password: '',
  passwordConfirmation: '',
})

watch(open, (isOpen) => {
  if (!isOpen) {
    photoPreviewOpen.value = false
    passwordState.currentPassword = ''
    passwordState.password = ''
    passwordState.passwordConfirmation = ''
  }
})

function openAvatarPicker() {
  if (avatarSubmitting.value) return
  avatarInputRef.value?.click()
}

function openPhotoPreview() {
  if (avatarSubmitting.value) return
  photoPreviewOpen.value = true
}

function onCameraClick(event: Event) {
  event.stopPropagation()
  openAvatarPicker()
}

async function onAvatarPick(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || avatarSubmitting.value) return

  if (!SAFE_RASTER_IMAGE_TYPES.includes(file.type as (typeof SAFE_RASTER_IMAGE_TYPES)[number])) {
    toast.add({ title: t('core.common.imageInvalidType'), color: 'error' })
    return
  }
  if (!isSafeRasterImage(file, 2)) {
    toast.add({ title: t('core.common.imageTooLarge', { size: 2 }), color: 'error' })
    return
  }

  avatarSubmitting.value = true
  try {
    const dataUrl = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(String(reader.result || ''))
      reader.onerror = () => reject(new Error('read failed'))
      reader.readAsDataURL(file)
    })
    await updateProfileAvatar(dataUrl)
    photoPreviewOpen.value = true
    toast.add({
      title: t('core.userProfile.photoUpdated'),
      description: t('core.userProfile.photoUpdatedDesc'),
      color: 'success',
    })
  }
  catch {
    toast.add({
      title: t('core.userProfile.photoUpdateFailed'),
      description: t('core.userProfile.photoUpdateFailedDesc'),
      color: 'error',
    })
  }
  finally {
    avatarSubmitting.value = false
  }
}

async function onRemoveAvatar() {
  if (avatarSubmitting.value || !hasCustomAvatar.value) return
  avatarSubmitting.value = true
  try {
    await removeProfileAvatar()
    photoPreviewOpen.value = false
    toast.add({
      title: t('core.userProfile.photoRemoved'),
      description: t('core.userProfile.photoRemovedDesc'),
      color: 'success',
    })
  }
  catch {
    toast.add({
      title: t('core.userProfile.photoRemoveFailed'),
      description: t('core.userProfile.photoRemoveFailedDesc'),
      color: 'error',
    })
  }
  finally {
    avatarSubmitting.value = false
  }
}

async function onPasswordSubmit(event: FormSubmitEvent<PasswordSchema>) {
  if (submitting.value) return
  submitting.value = true
  try {
    await changePassword({
      currentPassword: event.data.currentPassword,
      password: event.data.password,
      passwordConfirmation: event.data.passwordConfirmation,
    })
    toast.add({
      title: t('core.userProfile.passwordChanged'),
      description: t('core.userProfile.passwordChangedDesc'),
      color: 'success',
    })
    passwordState.currentPassword = ''
    passwordState.password = ''
    passwordState.passwordConfirmation = ''
  }
  catch {
    toast.add({
      title: t('core.userProfile.passwordChangeFailed'),
      description: t('core.userProfile.passwordChangeFailedDesc'),
      color: 'error',
    })
  }
  finally {
    submitting.value = false
  }
}

async function generateTelegramLinkCode() {
  if (linkCodeLoading.value || telegramLinked.value) return
  linkCodeLoading.value = true
  try {
    const result = await createTelegramLinkCode()
    linkCode.value = result.data.code
    toast.add({
      title: t('core.userProfile.telegramLinkCodeCreated'),
      description: t('core.userProfile.telegramLinkCodeCreatedDesc'),
      color: 'success',
    })
  }
  catch {
    toast.add({
      title: t('core.userProfile.telegramLinkCodeFailed'),
      color: 'error',
    })
  }
  finally {
    linkCodeLoading.value = false
  }
}
</script>

<template>
  <UModal
    v-model:open="open"
    scrollable
    :title="t('core.userProfile.title')"
    :dismissible="false"
    :close="{ color: 'primary', variant: 'outline', class: 'rounded-full' }"
    :ui="{
      overlay: 'place-items-start justify-items-center pt-[5vh] sm:pt-[5vh]',
      content: 'w-[calc(100%-2rem)] max-w-2xl sm:max-w-2xl',
    }"
  >
    <template #body>
      <div class="space-y-5">
        <div class="flex flex-col items-center gap-4 pb-1 text-center">
          <div class="relative inline-flex">
            <button
              type="button"
              class="rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
              :aria-label="t('core.userProfile.viewPhoto')"
              @click="openPhotoPreview"
            >
              <img
                :src="profile.avatar.src"
                :alt="profile.avatar.alt"
                class="size-16 rounded-full object-cover ring-2 ring-default sm:size-20"
                referrerpolicy="no-referrer"
              >
            </button>
            <span
              class="absolute -inset-e-2 -top-2 z-10 max-w-[6.5rem] truncate rounded-full bg-elevated px-2 py-0.5 text-[10px] font-semibold leading-none text-toned ring-1 ring-default shadow-sm"
              :title="profile.role"
            >
              {{ profile.role }}
            </span>
            <button
              type="button"
              class="absolute -bottom-1 -end-1 z-10 inline-flex size-7 items-center justify-center rounded-full border-2 border-default bg-default text-highlighted shadow-sm transition hover:bg-elevated disabled:opacity-60"
              :aria-label="t('core.userProfile.changePhoto')"
              :disabled="avatarSubmitting"
              @click="onCameraClick"
            >
              <UIcon
                :name="avatarSubmitting ? 'i-lucide-loader-circle' : 'i-lucide-camera'"
                class="size-4"
                :class="avatarSubmitting ? 'animate-spin' : ''"
              />
            </button>
            <input
              ref="avatarInputRef"
              type="file"
              class="hidden"
              :accept="SAFE_RASTER_IMAGE_ACCEPT"
              @change="onAvatarPick"
            >
          </div>
          <div class="min-w-0 max-w-full space-y-1">
            <h3 class="truncate text-lg font-semibold text-highlighted sm:text-xl">
              {{ profile.name }}
            </h3>
            <p class="truncate text-sm text-muted">
              {{ profile.email }}
            </p>
          </div>
        </div>

        <div class="space-y-3 border-t border-default pt-4">
          <h4 class="text-sm font-semibold text-highlighted">
            {{ t('core.userProfile.telegramTitle') }}
          </h4>
          <p class="text-sm text-muted">
            {{ t('core.userProfile.telegramHelp') }}
          </p>
          <div class="flex flex-wrap items-center gap-2">
            <UBadge :color="telegramLinked ? 'success' : 'neutral'" variant="subtle">
              {{ telegramLinked ? t('core.userProfile.telegramLinked') : t('core.userProfile.telegramNotLinked') }}
            </UBadge>
            <UButton
              v-if="!telegramLinked"
              size="sm"
              :loading="linkCodeLoading"
              @click="generateTelegramLinkCode"
            >
              {{ t('core.userProfile.generateLinkCode') }}
            </UButton>
          </div>
          <div
            v-if="linkCode"
            class="rounded-sm border border-default bg-elevated/40 px-3 py-2 font-mono text-sm"
          >
            /link {{ linkCode }}
          </div>
        </div>

        <div class="space-y-4 border-t border-default pt-4">
          <h4 class="text-sm font-semibold text-highlighted">
            {{ t('core.userProfile.tabs.password') }}
          </h4>

          <UForm
            :schema="passwordSchema"
            :state="passwordState"
            class="space-y-4"
            @submit="onPasswordSubmit"
          >
            <UFormField
              :label="t('core.userProfile.currentPassword')"
              name="currentPassword"
              required
              :help="t('core.userProfile.currentPasswordHelp')"
            >
              <UInput
                v-model="passwordState.currentPassword"
                type="password"
                autocomplete="current-password"
                class="w-full"
              />
            </UFormField>

            <UFormField
              :label="t('pages.forgetPassword.newPassword')"
              name="password"
              required
              :help="t('core.userProfile.newPasswordHelp')"
            >
              <UInput
                v-model="passwordState.password"
                type="password"
                autocomplete="new-password"
                class="w-full"
              />
            </UFormField>

            <UFormField
              :label="t('pages.forgetPassword.confirmPassword')"
              name="passwordConfirmation"
              required
              :help="t('core.userProfile.confirmPasswordHelp')"
            >
              <UInput
                v-model="passwordState.passwordConfirmation"
                type="password"
                autocomplete="new-password"
                class="w-full"
              />
            </UFormField>

            <div class="flex justify-end pt-1">
              <UButton
                type="submit"
                color="primary"
                :loading="submitting"
              >
                {{ t('core.userProfile.updatePassword') }}
              </UButton>
            </div>
          </UForm>
        </div>
      </div>
    </template>
  </UModal>

  <UModal
    v-model:open="photoPreviewOpen"
    :title="profile.name"
    :dismissible="false"
    :close="{ color: 'primary', variant: 'outline', class: 'rounded-full' }"
    :ui="{
      overlay: 'place-items-center justify-items-center',
      content: 'w-[calc(100%-2rem)] max-w-lg sm:max-w-2xl',
    }"
  >
    <template #body>
      <div class="relative overflow-hidden rounded-sm border border-default bg-elevated/30">
        <img
          :src="profile.avatar.src"
          :alt="profile.avatar.alt"
          class="mx-auto max-h-[min(80vh,36rem)] w-full object-contain"
          referrerpolicy="no-referrer"
        >
        <button
          v-if="hasCustomAvatar"
          type="button"
          class="absolute top-2 end-2 inline-flex size-9 items-center justify-center rounded-full bg-error text-white shadow-md transition hover:bg-error/90 disabled:opacity-60"
          :aria-label="t('core.userProfile.removePhoto')"
          :disabled="avatarSubmitting"
          @click="onRemoveAvatar"
        >
          <UIcon
            :name="avatarSubmitting ? 'i-lucide-loader-circle' : 'i-lucide-trash-2'"
            class="size-4"
            :class="avatarSubmitting ? 'animate-spin' : ''"
          />
        </button>
      </div>
    </template>
  </UModal>
</template>
