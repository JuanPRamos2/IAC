# Arquitectura políglota

PostgreSQL (negocio) · MongoDB (encuestas y bitácora) · Redis (sesión y caché).

La app Node orquesta las tres. No hay JOIN cruzado: se validan IDs en Postgres
y se persisten los mismos IDs en Mongo.

`consentimiento.seudonimo` es el único vínculo `empleado_id` ↔ `seudonimo_id`.
Las respuestas nunca guardan `empleado_id`.
