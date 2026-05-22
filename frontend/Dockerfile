# syntax=docker/dockerfile:1.7
# ---------- Stage 1: Install dependencies ----------
FROM node:20-alpine AS deps

WORKDIR /app

COPY package.json package-lock.json ./
# Cache npm's package tarballs across builds. This survives layer-cache
# invalidations (e.g. when package-lock.json changes), so npm ci stays fast
# even when the COPY layer above can't be reused.
RUN --mount=type=cache,target=/root/.npm,sharing=locked \
    npm ci --legacy-peer-deps --prefer-offline --no-audit --fund=false

# ---------- Stage 2: Build the application ----------
FROM node:20-alpine AS builder

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

ARG NEXT_PUBLIC_COLLAB_URL
ENV NEXT_PUBLIC_COLLAB_URL=$NEXT_PUBLIC_COLLAB_URL
ARG NEXT_PUBLIC_AUTH0_ENABLED
ENV NEXT_PUBLIC_AUTH0_ENABLED=$NEXT_PUBLIC_AUTH0_ENABLED
# In docker / self-host, rewrites + SSR fetches use the internal hostname
# to reach the backend; the public URL would loop through Caddy back into
# the container. next.config.ts's rewrites() runs at build, so this needs
# to be present at build time.
ARG BACKEND_INTERNAL_URL
ENV BACKEND_INTERNAL_URL=$BACKEND_INTERNAL_URL

ENV NEXT_TELEMETRY_DISABLED=1
# Persist Next.js / Turbopack's incremental build cache across builds.
RUN --mount=type=cache,target=/app/.next/cache,sharing=locked \
    npm run build

# ---------- Stage 3: Production runner ----------
FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Create non-root user
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# Copy only what's needed to run
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3457

ENV PORT=3457
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
