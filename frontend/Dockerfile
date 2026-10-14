# ── Stage 1: build ───────────────────────────────────────────────────────────
FROM node:20-alpine AS build

ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY

ENV HTTP_PROXY=${HTTP_PROXY} \
    HTTPS_PROXY=${HTTPS_PROXY} \
    NO_PROXY=${NO_PROXY}

# Tope explícito del heap de Node (MB). Dentro de un LXC, Node no ve el límite del cgroup:
# ve la RAM del host y se auto-configura un heap enorme, así que nunca colecta en serio y el
# build se arrastra (o lo mata el cgroup) en la fase `transforming` de vite. Con un tope
# chico GC entra antes y el build termina. Bajarlo a 1024 en servidores con 1-2 GB.
ARG NODE_MAX_OLD_SPACE=2048
ENV NODE_OPTIONS=--max-old-space-size=${NODE_MAX_OLD_SPACE}

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

# tsc y vite en pasos separados a propósito: así el log dice cuál de los dos tarda (o se
# cuelga) y el proceso de tsc libera su memoria antes de que arranque el bundle.
RUN npx tsc
RUN npx vite build

# ── Stage 2: serve ───────────────────────────────────────────────────────────
FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
