FROM node:22-alpine AS builder
WORKDIR /app
COPY frontend/ .

# Build-time environment variables for Vite
ARG VITE_API_URL=http://localhost:8000
ARG VITE_GOOGLE_CLIENT_ID=
ARG VITE_STRIPE_PUBLISHABLE_KEY=
ARG VITE_SENTRY_DSN=
ARG VITE_DISABLE_CHAT_MODE=false
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_GOOGLE_CLIENT_ID=$VITE_GOOGLE_CLIENT_ID
ENV VITE_STRIPE_PUBLISHABLE_KEY=$VITE_STRIPE_PUBLISHABLE_KEY
ENV VITE_SENTRY_DSN=$VITE_SENTRY_DSN
ENV VITE_DISABLE_CHAT_MODE=$VITE_DISABLE_CHAT_MODE

RUN if [ -f pnpm-lock.yaml ]; then corepack enable && corepack prepare pnpm@9.15.9 --activate && pnpm i --frozen-lockfile && pnpm run build; \
    elif [ -f yarn.lock ]; then yarn --frozen-lockfile && yarn build; \
    elif [ -f package-lock.json ]; then npm ci && npm run build; \
    else echo "Lockfile not found." && exit 1; \
    fi

FROM node:22-alpine AS runner
WORKDIR /app
RUN npm install -g serve
COPY --from=builder /app/dist ./dist

# Build manifest — written by stack_control.sh at build time.
# Inspect with: docker exec <container> cat /app/build-manifest.json
# Manifest is written to <repo>/build-manifest-frontend.json by
# scripts/stack_control.sh before invoking the build (file rather than
# build-arg avoids Linux ARG_MAX limits on large tracked_files lists).
ARG MANIFEST_FILE=build-manifest-frontend.json
COPY ${MANIFEST_FILE} /app/build-manifest.json

EXPOSE 3000
CMD ["serve", "-s", "dist", "-l", "3000"]