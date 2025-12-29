FROM node:18-alpine AS builder
WORKDIR /app
COPY frontend/ .

ARG BUILD_MODE=production
ARG VITE_API_URL="http://localhost:8000"
ARG VITE_GOOGLE_CLIENT_ID=""
ARG VITE_STRIPE_PUBLISHABLE_KEY=""
ARG VITE_SENTRY_DSN=""
ARG VITE_DISABLE_CHAT_MODE="false"
ARG VITE_DEV_AUTH_AUTOLOGIN="false"

RUN set -e; \
    env_file=".env.${BUILD_MODE:-production}"; \
    printf '%s\n' \
      "VITE_API_URL=${VITE_API_URL}" \
      "VITE_GOOGLE_CLIENT_ID=${VITE_GOOGLE_CLIENT_ID}" \
      "VITE_STRIPE_PUBLISHABLE_KEY=${VITE_STRIPE_PUBLISHABLE_KEY}" \
      "VITE_SENTRY_DSN=${VITE_SENTRY_DSN}" \
      "VITE_DISABLE_CHAT_MODE=${VITE_DISABLE_CHAT_MODE}" \
      "VITE_DEV_AUTH_AUTOLOGIN=${VITE_DEV_AUTH_AUTOLOGIN}" \
      > "$env_file"; \
    cp "$env_file" .env

RUN if [ -f yarn.lock ]; then yarn --frozen-lockfile && yarn build; \
    elif [ -f package-lock.json ]; then npm ci && npm run build; \
    elif [ -f pnpm-lock.yaml ]; then corepack enable pnpm && pnpm i --frozen-lockfile && pnpm run build; \
    else echo "Lockfile not found." && exit 1; \
    fi

FROM node:18-alpine AS runner
WORKDIR /app
RUN npm install -g serve
COPY --from=builder /app/dist ./dist
EXPOSE 1420
CMD ["serve", "-s", "dist", "-l", "1420"]
