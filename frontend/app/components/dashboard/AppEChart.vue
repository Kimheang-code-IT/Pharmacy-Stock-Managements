<script setup lang="ts">
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import type { EChartsCoreOption } from 'echarts/core'
import 'vue-echarts/style.css'

/**
 * Thin, theme-aware ECharts wrapper.
 * Registers only the modules used by dashboards/reports to keep chunks small;
 * echarts/vue-echarts are split into their own chunk by nuxt.config.
 */
use([CanvasRenderer, LineChart, BarChart, PieChart, GridComponent, TooltipComponent, LegendComponent])

const props = withDefaults(defineProps<{
  option: EChartsCoreOption
  height?: string
  ariaLabel?: string
}>(), {
  height: '100%',
  ariaLabel: '',
})

const colorMode = useColorMode()
type ChartExport = {
  getDataURL?: (opts?: Record<string, unknown>) => string
  chart?: { getDataURL?: (opts?: Record<string, unknown>) => string }
}

const chartRef = ref<ChartExport | null>(null)

const themedOption = computed<EChartsCoreOption>(() => {
  const dark = colorMode.value === 'dark'
  return {
    textStyle: {
      fontFamily: 'Inter, "Noto Sans Khmer", ui-sans-serif, system-ui, sans-serif',
      color: dark ? '#a1a1aa' : '#52525b',
    },
    tooltip: dark
      ? { backgroundColor: '#27272a', borderColor: '#3f3f46', textStyle: { color: '#e4e4e7' } }
      : {},
    ...props.option,
  }
})

function toPng() {
  const dark = colorMode.value === 'dark'
  const exporter = chartRef.value?.getDataURL || chartRef.value?.chart?.getDataURL
  return exporter?.({
    type: 'png',
    pixelRatio: 2,
    backgroundColor: dark ? '#18181b' : '#ffffff',
  }) || ''
}

defineExpose({ toPng })
</script>

<template>
  <ClientOnly class="block h-full min-h-0 w-full">
    <VChart
      ref="chartRef"
      class="h-full w-full min-h-0 min-w-0"
      :style="{ height: props.height }"
      :option="themedOption"
      autoresize
      :aria-label="props.ariaLabel"
      role="img"
    />
    <template #fallback>
      <div
        class="h-full w-full min-h-0 min-w-0 animate-pulse rounded-sm bg-muted/40"
        :style="{ height: props.height }"
        role="presentation"
      />
    </template>
  </ClientOnly>
</template>
