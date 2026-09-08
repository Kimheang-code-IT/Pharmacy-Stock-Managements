<script setup lang="ts">
import { useUserMenu } from '~/composables/layout/useUserMenu'

const props = withDefaults(defineProps<{
  collapsed?: boolean
  placement?: 'sidebar' | 'header'
}>(), {
  placement: 'sidebar',
})

const { user, items, aboutOpen, profileOpen } = useUserMenu()

const menuContent = computed(() => props.placement === 'header'
  ? { align: 'end' as const, collisionPadding: 12, side: 'bottom' as const }
  : {
      align: (props.collapsed ? 'end' : 'center') as 'end' | 'center',
      collisionPadding: 12,
      side: (props.collapsed ? 'right' : 'top') as 'right' | 'top',
    })
</script>

<template>
  <div :class="collapsed ? 'flex justify-center' : 'w-full'">
    <UDropdownMenu
      :items="items"
      :content="menuContent"
      :ui="{
        content: collapsed ? 'w-52 app-user-menu' : 'w-(--reka-dropdown-menu-trigger-width) app-user-menu',
        label: 'app-sidebar-text font-semibold',
        item: 'app-sidebar-text',
        itemLabel: 'app-sidebar-text',
        itemLeadingIcon: 'size-5 app-sidebar-text',
        itemTrailingIcon: 'size-5 app-sidebar-text',
      }"
    >
      <UButton
        v-if="collapsed"
        color="neutral"
        variant="ghost"
        square
        class="rounded-full p-0.5 data-[state=open]:bg-elevated"
        :aria-label="user.name"
      >
        <UAvatar
          :src="user.avatar.src"
          :alt="user.avatar.alt"
          size="md"
          class="ring-1 ring-default"
        />
      </UButton>

      <UButton
        v-else
        :avatar="user.avatar"
        :label="user.name"
        trailing-icon="i-lucide-chevrons-up-down"
        color="neutral"
        variant="ghost"
        block
        class="data-[state=open]:bg-elevated app-sidebar-text"
        :ui="{
          trailingIcon: 'app-sidebar-text',
          label: 'app-sidebar-text',
        }"
      />
    </UDropdownMenu>

    <LayoutAppAboutDialog v-model:open="aboutOpen" />
    <LayoutAppUserProfileDialog v-model:open="profileOpen" />
  </div>
</template>
