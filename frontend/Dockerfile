# Multi-stage Next.js standalone build.
# Rewrites (API_ORIGIN) and NEXT_PUBLIC_* values are baked in at build time, so pass them as build args.
FROM node:22-alpine AS deps
WORKDIR /app
COPY package*.json ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

FROM node:22-alpine AS build
WORKDIR /app
ARG API_ORIGIN=http://api:8000
ARG NEXT_PUBLIC_SITE_URL=http://localhost:3000
ARG NEXT_PUBLIC_DEMO_ACCOUNTS=0
ARG NEXT_PUBLIC_MAP_TILE_URL
ARG NEXT_PUBLIC_MAP_ATTRIBUTION
ENV API_ORIGIN=$API_ORIGIN NEXT_PUBLIC_SITE_URL=$NEXT_PUBLIC_SITE_URL NEXT_PUBLIC_DEMO_ACCOUNTS=$NEXT_PUBLIC_DEMO_ACCOUNTS \
    NEXT_PUBLIC_MAP_TILE_URL=$NEXT_PUBLIC_MAP_TILE_URL NEXT_PUBLIC_MAP_ATTRIBUTION=$NEXT_PUBLIC_MAP_ATTRIBUTION NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN mkdir -p public && npm run build

FROM node:22-alpine AS run
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN adduser -D -u 1001 web
COPY --from=build --chown=web /app/.next/standalone ./
COPY --from=build --chown=web /app/.next/static ./.next/static
COPY --from=build --chown=web /app/public ./public
USER web
EXPOSE 3000
CMD ["node", "server.js"]
