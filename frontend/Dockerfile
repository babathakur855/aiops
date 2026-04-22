# ── Stage 1: build ────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .

# Accept VPS public hostname/IP at build time so the browser can reach the backend
ARG NEXT_PUBLIC_API_URL=http://localhost:8011
ARG NEXT_PUBLIC_WS_URL=ws://localhost:8011
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL

RUN npm run build

# ── Stage 2: run (minimal image, standalone output) ───────────────
FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production

# Copy only the standalone output (no source, no node_modules)
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static     ./.next/static
COPY --from=builder /app/public           ./public

EXPOSE 3010

ENV PORT=3010
ENV HOSTNAME=0.0.0.0

CMD ["node", "server.js"]
