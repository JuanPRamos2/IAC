export const env = {
  port: Number(process.env.PORT || 3000),
  jwtSecret: process.env.JWT_SECRET || "dev-only-change-me",
  jwtExpiresSec: Number(process.env.JWT_EXPIRES_SEC || 900),
  loginMaxIntentos: Number(process.env.LOGIN_MAX_INTENTOS || 5),
  postgres: {
    host: process.env.POSTGRES_HOST || "localhost",
    port: Number(process.env.POSTGRES_PORT || 5432),
    database: process.env.POSTGRES_DB || "bienestar_nexum",
    user: process.env.POSTGRES_USER || "postgres",
    password: process.env.POSTGRES_PASSWORD || "postgres",
    max: 10,
  },
  mongoUrl: process.env.MONGO_URL || "mongodb://localhost:27017",
  mongoDb: process.env.MONGO_DB || "bienestar_nexum",
  redisUrl: process.env.REDIS_URL || "redis://localhost:6379",
};
