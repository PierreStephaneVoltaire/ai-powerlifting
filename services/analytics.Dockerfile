FROM node:24-bookworm-slim AS build
WORKDIR /opt/powerlifting
COPY package.json package-lock.json tsconfig.json ./
COPY backend/package.json backend/tsconfig.json ./backend/
COPY frontend/package.json ./frontend/
COPY packages/types ./packages/types
RUN npm ci --workspace=backend --workspace=packages/types
COPY backend/src ./backend/src
COPY services/operations ./services/operations
COPY services/calculation_constants.json ./services/calculation_constants.json
RUN npm run build --workspace=backend && npm prune --omit=dev --workspace=backend --workspace=packages/types

FROM node:24-bookworm-slim
WORKDIR /opt/powerlifting
COPY --from=build /opt/powerlifting/node_modules ./node_modules
COPY --from=build /opt/powerlifting/backend/dist ./backend/dist
COPY --from=build /opt/powerlifting/packages/types ./packages/types
COPY services/operations ./services/operations
COPY services/calculation_constants.json ./services/calculation_constants.json
USER node
WORKDIR /opt/powerlifting/backend
CMD ["node", "dist/analyticsSidecar.js"]
