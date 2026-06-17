# Frontend dev image. For production, build static assets and serve behind the API/edge.
FROM node:20-slim
WORKDIR /app

# Use the pnpm pinned in package.json (packageManager field), not corepack's "latest" — the
# latest pnpm now requires Node 22. The prompt flag keeps the non-interactive build from hanging.
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN corepack enable

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .

EXPOSE 5173
CMD ["pnpm", "dev", "--host", "0.0.0.0"]
