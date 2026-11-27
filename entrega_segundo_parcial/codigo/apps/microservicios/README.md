# Módulo de microservicios — segundo parcial

Ocho servicios, cada uno con su propia responsabilidad, su propio
contenedor y su propio contrato OpenAPI.

| Servicio | Responsable | Lenguaje | Responsabilidad | Puerto en developer |
|---|---|---|---|---|
| `auth-service` | Integrante 1 | Python | Emitir, renovar, validar y revocar tokens | 8101 |
| `users-service` | Integrante 1 | Python | Usuarios, perfiles, permisos y alcance | 8102 |
| `catalog-service` | Integrante 2 | Node | Unidades, instrumentos, versiones, reactivos y campañas | 8103 |
| `main-process-service` | Integrante 2 | Node | Responder una campaña y pedir apoyo | 8104 |
| `documents-service` | Integrante 3 | Python | Evidencias, avisos versionados y reportes | 8105 |
| `notifications-service` | Integrante 3 | Python | Notificaciones internas | 8106 |
| `queries-service` | Consultas | Python | Lectura de resultados publicados, con caché | 8107 |
| `reports-service` | Reportes | Python | Generar, sellar y entregar reportes | 8108 |

Cada uno expone:

- `GET /health/live` — el proceso responde
- `GET /health/ready` — sus dependencias responden
- `GET /openapi.json` — su contrato
- `GET /docs` — Swagger UI, servido por el propio servicio

## Dos lenguajes, un contrato

Seis servicios están en Python (Flask) y dos en Node (Express), porque los
escribieron integrantes distintos. Eso no es un accidente que haya que
disimular: es la prueba de que el contrato manda sobre la implementación.

Un cliente no puede saber en qué lenguaje está escrito el servicio al que
le habla, porque los ocho:

- firman y validan el JWT con el **mismo secreto** y el mismo algoritmo;
- leen la **misma sesión en Redis**, de modo que un `logout` revoca en todos;
- consultan `usuarios.perfil_permiso` **en cada petición** para autorizar;
- devuelven el **mismo sobre de error**, con los mismos siete códigos HTTP;
- serializan XML con las **mismas reglas** (envoltura plural, hijo singular,
  `xsi:nil`, namespace `http://nexum.com.mx/bienestar/v1`), de modo que un
  solo XSD describe las respuestas de los dos lenguajes;
- leen las variables de ambiente con los **mismos nombres**, para que un
  solo archivo `infra/ambientes/<ambiente>.env` levante los ocho.

Eso último no es cosmético: si cada lenguaje inventara sus nombres de
variable, ese archivo declararía la misma contraseña dos veces y bastaría
olvidar una para que un servicio se conectara a la base equivocada.

Las piezas compartidas viven en `comun/` (Python) y `comun-node/` (Node),
y ambas implementan las mismas reglas. Que sean dos archivos y no uno es el
costo de usar dos lenguajes; para que no se separen en silencio, hay una
prueba que compara las dos tablas de singularización y otra que compara las
constantes de permisos de Node contra `usuarios.permiso`.

## Levantar

```bash
cp infra/ambientes/developer.env.ejemplo infra/ambientes/developer.env

docker compose --env-file infra/ambientes/developer.env \
  -f infra/compose/docker-compose.base.yml \
  -f infra/compose/docker-compose.developer.yml \
  -f infra/compose/docker-compose.microservicios.yml up -d --wait
```

Después: <http://localhost:8101/docs> … `:8108`.

El orden de los puertos sigue a los integrantes y no al alfabeto, para que
en la demostración quien presenta su parte sepa en qué par de puertos está
sin consultar nada.

## Probar

```bash
python3 -m pytest pruebas/ -q      # 134 pruebas
```

La suite es repetible: limpia su propio estado en Redis al empezar y los
contadores del límite de consumo antes de cada prueba.

Dos cosas que la suite hace y conviene saber:

- **Levanta los servicios de Node de verdad.** No se pueden importar como
  los de Python, así que `pruebas/test_servicios_node.py` los arranca en un
  puerto libre y les habla por HTTP con un token emitido por
  `auth-service`. Eso es lo que prueba, y no un mock, que un token firmado
  en Python se valida en Node y que un `logout` revoca en los dos.
- **Sustituye MongoDB por `mongomock`**, porque en este entorno no se puede
  instalar. PostgreSQL y Redis sí son reales: una prueba contra una base
  simulada no habría detectado, por ejemplo, que `agregado.variacion` es
  una columna generada y no admite inserción.

## Lo que comparten, y por qué importa

`comun/` y `comun-node/` contienen la validación de JWT contra Redis, el
sobre de error, la serialización dual JSON/XML, la paginación, el límite de
consumo, las sondas de salud y el montaje de Swagger.

Que sea compartido no es comodidad: si cada servicio escribiera su propia
validación de JWT, bastaría que uno la hiciera mal para abrir un hueco en
todo el módulo.

Swagger UI se sirve desde cada servicio y no desde un CDN: si la red de la
demostración bloquea el CDN, la documentación igual abre.

## Autenticación común

El sistema web y `auth-service` firman con el **mismo secreto** y comparten
la **misma instancia de Redis**. Por eso:

- un token emitido por cualquiera sirve en los demás;
- un `logout` revoca en todos los componentes a la vez;
- el sistema web sigue operando si los microservicios se caen.

Esa última propiedad se demuestra apagando un servicio y recargando
`/administracion/usuarios` en el portal: el aviso cambia de
«users-service» a «base de datos» y la tabla sigue mostrando los usuarios.

**La degradación no es universal, y eso es deliberado.** Solo vale donde la
información existe de verdad en dos lados. La bandeja de notificaciones NO
cae a PostgreSQL, porque las notificaciones viven únicamente en MongoDB con
un índice TTL de 90 días: mostrar una bandeja vacía haría creer al usuario
que no tiene avisos pendientes cuando lo que pasa es que el servicio está
caído. En ese caso la pantalla lo dice y explica qué se está perdiendo.

Otra asimetría del mismo tipo: ante una caída de Redis, los microservicios
rechazan con 503 y el sistema web degrada y sigue. Los servicios atienden a
clientes externos y ante la duda no abren; el portal ya tiene una sesión
establecida y negar todo lo dejaría inservible.

## Lo que ningún servicio hace

- **Ninguno recibe `empleado_id`** ni otro identificador directo de
  persona. `main-process-service` rechaza la petición completa con 400
  `PRIVACIDAD_D01` en lugar de limpiar el campo en silencio: un cliente que
  manda `empleado_id` está programado con un modelo equivocado del sistema
  y conviene que lo sepa. `comun/mongo.py` y `comun-node/mongo.js`
  verifican el documento completo antes de escribir, y el validador
  `$jsonSchema` de MongoDB lo rechaza como última barrera.
- **`queries-service` y `reports-service` nunca invocan
  `agregado.fn_calcular_agregado_protegido`.** Esa función consume
  presupuesto de épsilon cada vez que corre, así que un servicio de
  consultas que la llamara gastaría privacidad en cada recarga de pantalla
  y dejaría a la campaña sin poder publicar resultados nuevos. Hay una
  prueba que lee el presupuesto, hace diez consultas y comprueba que el
  épsilon consumido no se movió.
- **`notifications-service` no deja pasar cifras decimales** en el título
  ni en el mensaje. Publicar «la carga percibida bajó a 2.9» por esa vía
  entregaría el dato sin ruido de Laplace, sin umbral *k* y sin descontar
  nada del presupuesto: el mecanismo de privacidad diferencial solo protege
  si *todas* las salidas pasan por él.
- **Ningún servicio escribe directo en el esquema `autoreporte`.** El rol de
  la aplicación no tiene INSERT ahí; las respuestas se registran a través de
  una función `SECURITY DEFINER` con `search_path` fijado, que hace cumplir
  RN-01, RN-02, que la campaña esté abierta y que la unidad salga del padrón.

## Contratos

| Qué | Dónde | Cómo se mantiene |
|---|---|---|
| OpenAPI de los seis servicios en Python | `GET /openapi.json` de cada uno | se construye en `comun/openapi.py` |
| OpenAPI de los dos de Node | `apps/microservicios/<svc>/openapi.yaml` | **generado** por `contratos/generar_openapi_node.py` |
| 9 esquemas XSD | `contratos/xml/` | validados contra respuestas reales en `pruebas/test_contratos_xml.py` y `test_servicios_node.py` |
| 64 esquemas JSON | `contratos/json/` | **generados** por `contratos/generar_json.py` |

Los contratos de Node se generan en lugar de escribirse a mano por un
motivo concreto: los dos servicios sirven un archivo estático, así que no
pueden construir su contrato con `comun/openapi.py`. Escritos a mano
documentaban un puerto que no era, una sonda `/health` que no existe y
ningún `components.schemas` — y declaraban un formato de error distinto al
que el módulo devuelve de verdad.
