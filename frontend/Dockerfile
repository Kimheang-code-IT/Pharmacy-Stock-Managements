FROM node:22-alpine AS base
RUN corepack enable && corepack prepare pnpm@10.30.3 --activate
WORKDIR /app

FROM base AS deps
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

FROM base AS build
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ARG NUXT_PUBLIC_API_BASE=same-origin
ARG NUXT_PUBLIC_SITE_URL=
ARG NUXT_PUBLIC_APP_VERSION=1.0.0
ENV NUXT_PUBLIC_API_BASE=$NUXT_PUBLIC_API_BASE
ENV NUXT_PUBLIC_SITE_URL=$NUXT_PUBLIC_SITE_URL
ENV NUXT_PUBLIC_APP_VERSION=$NUXT_PUBLIC_APP_VERSION
RUN pnpm build

FROM nginx:1.27-alpine AS runner
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/.output/public /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=5 \
    CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
