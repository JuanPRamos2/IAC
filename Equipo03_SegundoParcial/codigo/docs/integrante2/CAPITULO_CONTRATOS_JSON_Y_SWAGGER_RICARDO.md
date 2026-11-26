# Capítulos del Expediente — Contratos JSON y Swagger (OpenAPI 3.0.3)

**Autor:** Ricardo Arath Sánchez Aguirre (#583928) — Integrante 2  
**Proyecto:** Bienestar Nexum · Equipo 03 · UDEM  
**Alcance:** Apartados de **Contratos JSON** y **Swagger / OpenAPI** del expediente de 32 secciones, alineados al código vigente en la rama integrada (`24` microservicios, `109` esquemas JSON Schema y `16` esquemas XSD).

---

## 1. Contratos JSON (JSON Schema Draft 2020-12)

### 1.1 Estrategia de fuente única de verdad
En **Bienestar Nexum**, los contratos JSON **no se redactan por duplicado a mano** respecto a la API real. Cada microservicio declara sus modelos de petición y respuesta en su especificación OpenAPI 3.0.3 (`contrato.py` en Python o `src/openapi.js` en Node.js), y el generador automatizado `contratos/generar_json.py` extrae todos los esquemas hacia `contratos/json/<NombreModelo>.schema.json` bajo el estándar **JSON Schema Draft 2020-12** (`https://json-schema.org/draft/2020-12/schema`).

Beneficios arquitectónicos:
- Impide que la documentación diverja de lo que los servicios realmente validan o responden.
- Permite que clientes estrictamente JSON como la aplicación móvil Android (`apps/movil/`, Kotlin) y pruebas automatizadas validen cargas útiles sin levantar cada microservicio.
- Homologa el sobre estándar de error (`Error.schema.json`) y la paginación (`Paginacion.schema.json`) entre los 18 servicios en Python (Flask) y los 6 servicios en Node.js (Express).

### 1.2 Inventario de los 109 esquemas en `contratos/json/`
Actualmente el directorio `contratos/json/` contiene **109 archivos `.schema.json`** verificados mediante `Draft202012Validator.check_schema`:

| Dominio / Servicios | Esquemas `.schema.json` representativos |
|---|---|
| **Comunes y Seguridad (`comun`, `auth-service`, `users-service`)** | `Error`, `Paginacion`, `SolicitudLogin`, `Sesion`, `SolicitudRenovar`, `Validacion`, `SolicitudRecuperarAcceso`, `RespuestaRecuperarSolicitada`, `SolicitudConfirmarRecuperacion`, `RespuestaRecuperarConfirmada`, `Usuario`, `ListaUsuarios`, `SolicitudAlta`, `SolicitudBaja` |
| **Catálogos, Encuestas y Proceso Principal (`catalog`, `main-process`, `survey`)** | `Campania`, `ListaCampanias`, `Instrumento`, `ListaInstrumentos`, `VersionInstrumento`, `ListaVersiones`, `Reactivo`, `ListaReactivos`, `ReactivoDeVersion`, `ListaReactivosVersion`, `UnidadOrganizacional`, `ListaUnidades`, `FuenteAutorizada`, `Dimension`, `ResumenCatalogo`, `SolicitudRespuesta`, `AcuseParticipacion`, `AcuseRespuesta`, `EventoProceso`, `Cuestionario`, `DetalleCuestionario`, `ListaCuestionarios`, `ReactivoCuestionario`, `Borrador`, `SolicitudBorrador`, `BorradorGuardado`, `SolicitudRespuestasCuestionario`, `RegistroRespuestaCuestionario`, `ParticipacionPropia` |
| **Organización, Indicadores y Apoyo (`organizational`, `indicators`, `support`)** | `ArbolOrganizacional`, `NodoArbolOrganizacional`, `ListaUnidadesOrganizacion`, `RespuestaUnidadOrganizacion`, `SolicitudAltaUnidad`, `SolicitudActualizacionUnidad`, `Indicador`, `ListaIndicadores`, `AgregadoIndicador`, `FilaAgregado`, `RespuestaAgregados`, `SolicitudCalculoIndicadores`, `RespuestaCalculoIndicadores`, `PuntoHistoricoIndicador`, `RespuestaHistorico`, `SolicitudApoyo`, `SolicitudApoyoAlta`, `SolicitudApoyoCreacion`, `ListaSolicitudesApoyo`, `CambioEstadoSolicitud`, `SolicitudCambioEstadoApoyo`, `SolicitudMensajeApoyo`, `RespuestaMensajeApoyo` |
| **Documentos, Notificaciones, Consentimiento y Privacidad** | `Documento`, `SolicitudDocumento`, `Notificacion`, `SolicitudEnvio`, `CambioConsentimiento`, `OperacionEntrante`, `IdentificadorEntrante`, `UnidadEntrante`, `ResultadoOperacion`, `RechazoFila` |
| **Analítica, Tendencias, Reportes, Exportación y Monitoreo** | `Analisis`, `Tendencia`, `UnidadPriorizada`, `Corrida`, `Deteccion`, `Hallazgo`, `Regla`, `Simulacion`, `SolicitudEvaluar`, `SolicitudSimular`, `UnidadNoEvaluable`, `PuntoTendencia`, `ResumenTendencia`, `PlanIntervencion`, `Evaluacion`, `Cobertura`, `FilaParticipacion`, `FilaTablero`, `Reporte`, `SolicitudReporte`, `TipoReporte`, `Exportacion`, `Parametro`, `CambioParametro`, `EstadoPresupuesto`, `EstadoCache`, `SolicitudInvalidar`, `EstadoComponente`, `SolicitudVerificar`, `Verificacion` |

### 1.3 Validación automatizada de contratos JSON (`pruebas/test_contratos_json.py`)
El archivo `pruebas/test_contratos_json.py` comprueba dos garantías fundamentales usando `jsonschema.Draft202012Validator`:
1. **Validez sintáctica universal (`test_todos_los_esquemas_son_validos`):** recorre todos los `.schema.json` en `contratos/json/` y confirma que son esquemas Draft 2020-12 bien formados.
2. **Validación contra tráfico HTTP real y rechazo negativo:** contrasta respuestas en vivo de `auth-service` (`Sesion`, `Validacion`), `users-service` (`ListaUsuarios`, `Usuario`, `Error` 403/422), `documents-service` (`Documento`) y `notifications-service` (`Notificacion`), y confirma en `test_una_solicitud_mal_formada_no_valida` que el esquema sí rechaza entradas inválidas.

---

## 2. Swagger / OpenAPI 3.0.3 en los 24 Microservicios

### 2.1 Arquitectura compartida (Python y Node.js)
Para garantizar homogeneidad entre ambos lenguajes:
- **Python (18 microservicios):** `apps/microservicios/comun/comun/openapi.py` define `_componentes_comunes()`, `PARAMS_PAGINACION`, `RESPUESTAS_ERROR` y construye la especificación OpenAPI 3.0.3 dinámicamente por servicio.
- **Node.js (6 microservicios):** `apps/microservicios/comun-node/src/openapi.js` replica exactamente la misma estructura (`crearContratoOpenApi`, `montarSwagger`), incorporando `servers`, esquema de seguridad `bearerAuth` (`type: http`, `scheme: bearer`, `bearerFormat: JWT`) a nivel raíz y las **7 respuestas comunes de error** con ejemplos tanto en `application/json` como en `application/xml` (`http://nexum.com.mx/bienestar/v1`). Además, `contratos/generar_openapi_node.py` sincroniza los archivos estáticos `openapi.json` y `openapi.yaml`.

### 2.2 Swagger UI autónomo (sin dependencia de CDN)
Cada uno de los 24 servicios expone localmente:
- `GET /openapi.json` — contrato OpenAPI 3.0.3 completo en JSON.
- `GET /docs` — interfaz interactiva **Swagger UI**, servida con archivos estáticos embebidos en el repositorio (`estaticos/swagger/swagger-ui-bundle.js` y `swagger-ui.css`), de modo que funciona incluso en entornos aislados o sin acceso a CDNs externos.

### 2.3 Mapa de puertos y rutas Swagger clave para demostración

| Puerto (`developer`) | Servicio | Lenguaje | URL Swagger local | Endpoints destacados en demostración |
|---:|---|---|---|---|
| `8101` | `auth-service` | Python | `http://localhost:8101/docs` | `POST /api/v1/auth/login`, `POST /api/v1/auth/renovar`, `POST /api/v1/auth/logout`, `GET /api/v1/auth/validar`, `POST /api/v1/auth/recuperar/solicitar` y `/confirmar` |
| `8103` | `catalog-service` | Node.js | `http://localhost:8103/docs` | CRUD de `/api/v1/catalogos/unidades`, `/instrumentos`, `/reactivos`, `/campanias` |
| `8104` | `main-process-service` | Node.js | `http://localhost:8104/docs` | `POST /api/v1/encuestas/respuestas` (regla D-01), `/solicitudes-apoyo` |
| `8105` | `documents-service` | Python | `http://localhost:8105/docs` | `POST /api/v1/documentos/archivos`, `GET /api/v1/documentos/archivos/{sha256}/url`, `GET /api/v1/documentos/{documento_id}/url-firmada` |
| `8109` | `algorithms-service` | Python | `http://localhost:8109/docs` | `GET /api/v1/algoritmos/analisis`, `POST /api/v1/algoritmos/evaluar` |
| `8112` | `survey-service` | Node.js | `http://localhost:8112/docs` | `/api/v1/cuestionarios`, `/borrador`, `/respuestas` |
| `8113` | `indicators-service` | Node.js | `http://localhost:8113/docs` | `/api/v1/indicadores/agregados`, `/historico` (umbral $k \ge 5$) |
| `8116` | `support-service` | Node.js | `http://localhost:8116/docs` | `/api/v1/apoyo/solicitudes` y máquina de estados |
| `8117` | `organizational-service` | Node.js | `http://localhost:8117/docs` | `/api/v1/organizacion/unidades`, `/arbol` |
| `8123` | `monitoring-service` | Python | `http://localhost:8123/docs` | `/api/v1/monitoreo/salud`, `/errores`, `/alertas` |

*(Los 14 servicios restantes `8102, 8106–8108, 8110–8111, 8114–8115, 8118–8122, 8124` siguen exactamente la misma convención `http://localhost:<puerto>/docs` y `/openapi.json`).*
