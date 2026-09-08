// nuxt.config.ts
// https://nuxt.com/docs/api/configuration/nuxt-config

export default defineNuxtConfig({
  // Generate a client-side static application for nginx/Docker deployment.
  ssr: false,

  modules: [
    '@nuxt/ui',
    '@vueuse/nuxt',
    '@nuxtjs/i18n',
    '@nuxt/fonts',
    '@pinia/nuxt',
    '@nuxt/eslint',
  ],

  app: {
    head: {
      title: 'Yoeun Sokhon Pharmacy',
      htmlAttrs: {
        lang: 'en',
      },
      meta: [
        { name: 'format-detection', content: 'telephone=no' },
        { name: 'theme-color', content: '#000000' },
        {
          name: 'description',
          content: 'Yoeun Sokhon Pharmacy — stock, sales and point-of-sale management.',
        },
      ],
      link: [
        { rel: 'icon', type: 'image/png', href: '/logo.png' },
        { rel: 'apple-touch-icon', href: '/logo.png' },
      ],
    },
  },

  devtools: {
    enabled: import.meta.env.DEV
  },

  devServer: {
    host: '0.0.0.0',
    port: 3000,
  },

  runtimeConfig: {
    // Overridden at runtime by NUXT_API_INTERNAL_BASE (Docker: http://api:8000).
    apiInternalBase: 'http://127.0.0.1:8000',
    public: {
      // `auto` uses the page hostname with port 8000 — works for LAN/Wi‑Fi access.
      apiBase: import.meta.env.NUXT_PUBLIC_API_BASE || 'auto',
      apiTimeoutMs: Number(import.meta.env.NUXT_PUBLIC_API_TIMEOUT_MS || 30000),
      authMode: import.meta.env.NUXT_PUBLIC_AUTH_MODE === 'cookie' ? 'cookie' : 'bearer',
      csrfCookieName: import.meta.env.NUXT_PUBLIC_CSRF_COOKIE_NAME || 'XSRF-TOKEN',
      csrfHeaderName: import.meta.env.NUXT_PUBLIC_CSRF_HEADER_NAME || 'X-CSRF-Token',
      useMockData: import.meta.env.NUXT_PUBLIC_USE_MOCK_DATA === 'true',
      appVersion: import.meta.env.NUXT_PUBLIC_APP_VERSION || '0.1.0',
      // Canonical public origin for Open Graph / Twitter image URLs (no trailing slash).
      // Example: https://app.stockpos.example — required for link previews to show images.
      siteUrl: import.meta.env.NUXT_PUBLIC_SITE_URL || '',
    }
  },

  imports: {
    dirs: ['utils/**'],
  },

  css: ['~/assets/css/main.css'],

  // Google Fonts via @nuxt/fonts — Inter (Latin) + Noto Sans Khmer (Khmer script)
  fonts: {
    provider: 'google',
    defaults: {
      weights: [400, 500, 600, 700],
      styles: ['normal'],
      subsets: ['latin', 'latin-ext'],
    },
    families: [
      {
        name: 'Inter',
        provider: 'google',
        weights: [400, 500, 600, 700],
        subsets: ['latin', 'latin-ext'],
      },
      {
        name: 'Noto Sans Khmer',
        provider: 'google',
        weights: [400, 500, 600, 700],
        subsets: ['khmer'],
        global: true,
      },
    ],
  },

  // Menu icons live in .ts/.vue — keep the scan tight for a smaller first client bundle
  icon: {
    serverBundle: 'local',
    clientBundle: {
      scan: {
        globInclude: [
          'app/components/**/*.{vue,ts}',
          'app/composables/**/*.ts',
          'app/config/**/*.ts',
          'app/layouts/**/*.vue',
          'app/pages/**/*.vue',
        ],
      },
      sizeLimitKb: 256,
    },
  },

  i18n: {
    locales: [
      {
        code: 'en',
        name: 'English',
        file: 'en.json',
      },
      {
        code: 'km',
        name: 'ភាសាខ្មែរ',
        file: 'km.json',
      },
    ],
    defaultLocale: 'en',
    strategy: 'no_prefix',
    langDir: 'locales',
    detectBrowserLanguage: false,
  },

  routeRules: {
    '/**': {
      headers: {
        'x-content-type-options': 'nosniff',
        'referrer-policy': 'strict-origin-when-cross-origin',
        'x-frame-options': 'DENY',
        'permissions-policy': 'camera=(), microphone=(), geolocation=()',
        'cross-origin-opener-policy': 'same-origin',
        'cross-origin-resource-policy': 'same-site',
        'x-permitted-cross-domain-policies': 'none',
        ...(import.meta.env.PROD
          ? { 'strict-transport-security': 'max-age=31536000; includeSubDomains' }
          : {}),
      },
    },
  },

  nitro: {
    preset: 'static',
  },

  compatibilityDate: '2024-07-11',

  vite: {
    build: {
      chunkSizeWarningLimit: 1000,
      rollupOptions: {
        output: {
          manualChunks(id) {
            // CSS/virtual style modules must stay with Vite's CSS pipeline or Nitro
            // fails with UNRESOLVED_IMPORT on `*-styles-*.mjs-!~{…}~.js`.
            if (
              id.includes('.css')
              || id.includes('?vue&type=style')
              || id.includes('&lang.css')
              || id.includes('type=style')
            ) {
              return
            }
            if (id.includes('node_modules/echarts') || id.includes('vue-echarts')) return 'echarts'
          },
        },
      },
    },
    // Pre-bundle the heavy deps used by the landing route up front, so the
    // first dashboard visit does not pause while Vite optimizes new modules
    // and force-reloads the page.
    optimizeDeps: {
      include: [
        '@vueuse/core',
        '@internationalized/date',
        'zod',
        '@tanstack/vue-table',
        'echarts/core',
        'echarts/charts',
        'echarts/components',
        'echarts/renderers',
        'vue-echarts',
      ],
    },
  }
})
