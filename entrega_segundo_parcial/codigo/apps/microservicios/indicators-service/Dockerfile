# indicators-service — Puerto 8113 (Integrante 2: Ricardo)
FROM node:20-alpine

RUN addgroup -S servicio && adduser -S servicio -G servicio

WORKDIR /srv
COPY comun-node/package.json ./comun-node/package.json
COPY indicators-service/package.json ./indicators-service/package.json

WORKDIR /srv/comun-node
RUN npm install --omit=dev --no-audit --no-fund

WORKDIR /srv/indicators-service
RUN npm install --omit=dev --no-audit --no-fund

COPY comun-node /srv/comun-node
COPY indicators-service/src /srv/indicators-service/src

ENV NODE_ENV=production \
    NOMBRE_SERVICIO=indicators-service \
    PUERTO=8113
EXPOSE 8113

USER servicio

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD node -e "fetch('http://127.0.0.1:8113/health/live').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node", "src/server.js"]
