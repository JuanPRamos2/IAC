# Integración del tercer parcial

Esta rama junta lo que cada integrante subió para el tercer parcial, sin
perder el trabajo de los demás.

- **Integrante 1.** Despliegue en Google Compute Engine: `docker-compose.gcp.yml`,
  `infra/caddy/Caddyfile` y el bucket `nexum-610248-evidencias`. El portal
  compartido es https://34.41.26.94.sslip.io mientras la máquina
  `nexum-equipo03` esté encendida. La llave `signer.json` no está en Git.
- **Integrante 2.** Seguridad, recuperación de acceso, contratos y la reconexión
  de Redis. Su migración sigue siendo
  `018_tercer_parcial_seguridad_y_buckets.sql`.
- **Integrante 3 y Integrante 4.** Análisis complejo (paquete `analitica`), Locust,
  datos masivos y las migraciones `019`, `020` y
  `021_analisis_complejo_y_rendimiento.sql`. El 021 es el 018 de su paquete,
  renumerado para no pisar la migración de Integrante 2.

La base de la rama es `Integrante 2`. Lo nuevo de `main` era el archivo
`paquete del tercer parcial`; su código quedó incorporado aquí.
