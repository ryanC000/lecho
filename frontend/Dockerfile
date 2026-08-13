# Static bundle behind nginx. The frontend is not an application server — this
# image exists so the Ingress can front the bundle and the API on ONE origin,
# which is what removes CORS and mixed-content from the deployment entirely.
#
#   docker build -t lecho-frontend:dev ./frontend
#
# VITE_API_BASE is empty on purpose: Vite bakes it in at build time, and an
# empty base makes api/client.js emit relative URLs ("/jobs"), so the bundle is
# not pinned to any hostname. Overriding it here would hard-code one.
FROM node:20-alpine AS build

WORKDIR /app

# npm install, not npm ci: package-lock.json is gitignored, so a clean clone has
# no lockfile for ci to read.
COPY package.json ./
RUN npm install

COPY . ./

ARG VITE_API_BASE=""
ARG VITE_GOOGLE_CLIENT_ID=""
ENV VITE_API_BASE=$VITE_API_BASE \
    VITE_GOOGLE_CLIENT_ID=$VITE_GOOGLE_CLIENT_ID
RUN npm run build

FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
