# organizational-service — Puerto 8117 (Integrante 2: Ricardo)
FROM node:20-alpine

RUN addgroup -S servicio && adduser -S servicio -G servicio

WORKDIR /srv
COPY comun-node/package.json ./comun-node/package.json
COPY organizational-service/package.json ./organizational-service/package.json

WORKDIR /srv/comun-node
RUN npm install --omit=dev --no-audit --no-fund

WORKDIR /srv/organizational-service
RUN npm install --omit=dev --no-audit --no-fund

COPY comun-node /srv/comun-node
COPY organizational-service/src /srv/organizational-service/src

ENV NODE_ENV=production \
    NOMBRE_SERVICIO=organizational-service \
    PUERTO=8117
EXPOSE 8117

USER servicio

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD node -e "fetch('http://127.0.0.1:8117/health/live').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node", "src/server.js"]
