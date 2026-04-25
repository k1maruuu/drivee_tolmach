FROM node:20-alpine AS deps
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci


FROM node:20-alpine AS builder
WORKDIR /app

# Where Next.js server proxies /api/* (Compose: backend service; host `next dev`: 127.0.0.1).
ARG NEXT_INTERNAL_API_DEST=http://backend:8000
ENV NEXT_INTERNAL_API_DEST=$NEXT_INTERNAL_API_DEST

# For docker-compose proxy mode we want same-origin requests in browser.
# If you need absolute URL (local dev), pass it explicitly as build-arg.
ARG NEXT_PUBLIC_API_URL=
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

COPY --from=deps /app/node_modules ./node_modules
COPY . .

RUN npm run build


FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production

# Next standalone output
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000
ENV PORT=3000

CMD ["node", "server.js"]

