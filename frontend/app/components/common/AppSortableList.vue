<script setup lang="ts" generic="T extends { id: string }">
const props = defineProps<{
  items: T[]
  disabled?: boolean
}>()

const emit = defineEmits<{
  reorder: [items: T[]]
}>()

const dragId = ref<string | null>(null)
const overId = ref<string | null>(null)

function onDragStart(id: string, event: DragEvent) {
  if (props.disabled) {
    event.preventDefault()
    return
  }
  dragId.value = id
  event.dataTransfer?.setData('text/plain', id)
  if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move'
}

function onDragOver(id: string, event: DragEvent) {
  event.preventDefault()
  overId.value = id
}

function onDrop(targetId: string) {
  const sourceId = dragId.value
  dragId.value = null
  overId.value = null
  if (!sourceId || sourceId === targetId) return

  const next = [...props.items]
  const from = next.findIndex(i => i.id === sourceId)
  const to = next.findIndex(i => i.id === targetId)
  if (from < 0 || to < 0) return
  const [moved] = next.splice(from, 1)
  if (!moved) return
  next.splice(to, 0, moved)
  emit('reorder', next)
}

function onDragEnd() {
  dragId.value = null
  overId.value = null
}
</script>

<template>
  <div class="flex flex-col gap-2">
    <div
      v-for="item in items"
      :key="item.id"
      class="rounded-sm border border-default bg-default transition"
      :class="[
        overId === item.id && dragId !== item.id ? 'border-primary ring-1 ring-primary/30' : '',
        dragId === item.id ? 'opacity-60' : '',
      ]"
      :draggable="!disabled"
      @dragstart="onDragStart(item.id, $event)"
      @dragover="onDragOver(item.id, $event)"
      @drop.prevent="onDrop(item.id)"
      @dragend="onDragEnd"
    >
      <div class="flex items-stretch gap-2 p-2">
        <UButton
          type="button"
          icon="i-lucide-grip-vertical"
          color="neutral"
          variant="ghost"
          size="xs"
          class="cursor-grab text-muted active:cursor-grabbing"
          :disabled="disabled"
          aria-label="Reorder"
        />
        <div class="min-w-0 flex-1">
          <slot :item="item" />
        </div>
      </div>
    </div>
    <p v-if="!items.length" class="py-6 text-center text-sm text-muted">
      <slot name="empty" />
    </p>
  </div>
</template>
