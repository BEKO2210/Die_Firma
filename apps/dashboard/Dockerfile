# Dashboard image (review §10). Build context = apps/dashboard:
#   docker build -t die-firma-dashboard apps/dashboard
FROM node:22-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:22-slim AS runtime
ENV NODE_ENV=production \
    HOST=0.0.0.0 \
    PORT=4321
WORKDIR /app
# better-sqlite3 ships a prebuilt binary; copy node_modules + the standalone build.
COPY --from=build /app/node_modules /app/node_modules
COPY --from=build /app/dist /app/dist
COPY --from=build /app/package.json /app/package.json
EXPOSE 4321
CMD ["node", "./dist/server/entry.mjs"]
