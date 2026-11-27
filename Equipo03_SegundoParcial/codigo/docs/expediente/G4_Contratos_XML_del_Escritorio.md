# Contratos XML de la aplicación de escritorio

**Expediente NEXUM — Equipo 03 · Capítulo de Gerardo Quiroga Ramírez
(#650313)**

Contratos: `contratos/xml/` (16 XSD). Cliente: `apps/escritorio/cliente.py`.
Pruebas: `pruebas/test_escritorio.py`, `pruebas/test_contratos_xml.py`.

---

## 1. Por qué la aplicación de escritorio habla XML

La arquitectura obligatoria pide dos clientes con formatos distintos: la
aplicación móvil consume **JSON** y la de escritorio **XML**. No es un
capricho del enunciado — es lo que obliga a que el contrato mande sobre la
implementación.

Si los dos clientes hablaran JSON, el servicio podría devolver lo que le
saliera y el cliente adaptarse. Con dos formatos, el servicio tiene que
tener una **representación** de la respuesta y dos serializaciones de esa
representación, y eso se nota en el diseño.

---

## 2. Cómo se negocia el formato

Lectura (`Accept`) y escritura (`Content-Type`):

```
GET  → Accept: application/xml
POST → Content-Type: application/xml; charset=utf-8
       Accept: application/xml
```

**El formato se decide por la cabecera, no por el contenido.** Adivinar
mirando si el primer carácter es `{` o `<` funcionaría casi siempre, y el
«casi» es el problema: un cuerpo vacío, un BOM o un espacio al principio
cambiarían la interpretación sin que nada lo avise.

### Un defecto que esto encontró

Los servicios leían el cuerpo con `request.get_json()`. El efecto: una
aplicación cliente que mandara XML recibía un 422 por «campos
obligatorios» **aunque los hubiera mandado todos**, porque `get_json()`
devolvía `None` y el servicio veía un cuerpo vacío.

Como la aplicación de escritorio consume XML exclusivamente, sin
`cuerpo_peticion()` —la función de `comun` que lee JSON o XML según
`Content-Type`— **no podía hacer ninguna operación de escritura**.

---

## 3. El espacio de nombres

```
http://nexum.com.mx/bienestar/v1
```

Uno solo, para los 24 servicios, en los dos lenguajes. El cliente busca
siempre con el nombre calificado:

```python
nodo.find(f"{{{ESPACIO}}}usuario")
```

Que sea uno solo es lo que permite que el cliente de escritorio hable con
servicios de Python y de Node sin saber cuál es cuál. Seis de los
veinticuatro están en Express y el cliente no los distingue.

---

## 4. Los 16 esquemas

| XSD | Cubre |
|---|---|
| `comun.xsd` | el sobre de error y los tipos compartidos |
| `sesion.xsd` | login, validación, renovación, cierre |
| `usuarios.xsd` | usuarios, perfiles, permisos |
| `catalogos.xsd` | dimensiones, reactivos, instrumentos |
| `cuestionarios.xsd` | campañas y autorreporte |
| `consultas.xsd` | agregados y participación |
| `reportes.xsd` | reportes de bienestar |
| `documentos.xsd` | evidencias y avisos |
| `notificaciones.xsd` | bandeja y preferencias |
| `algoritmos.xsd` | reglas, evaluación y análisis |
| `indicadores.xsd` | indicadores |
| `organizacion.xsd` | estructura organizacional |
| `proceso.xsd` | proceso principal |
| `apoyo.xsd` | solicitudes de apoyo |
| `exportacion.xsd` | exportaciones |
| `integracion.xsd` | integración y sincronización |

### El sobre de error es el mismo que en JSON

```xml
<error xmlns="http://nexum.com.mx/bienestar/v1">
  <codigo>VALIDACION</codigo>
  <mensaje>La solicitud tiene campos invalidos.</mensaje>
  <correlacion_id>d55d3d7df5be4d28</correlacion_id>
  <detalles>
    <detalle><campo>intervencion_id</campo><problema>abc</problema></detalle>
  </detalles>
</error>
```

Mismo `codigo`, mismo `correlacion_id`. Un cliente escribe **un** manejador
de errores, y el identificador de correlación permite seguir una operación
que pasó por tres servicios con un solo número en la bitácora.

---

## 5. El cliente valida lo que recibe

Esto es lo que más distingue a este cliente de uno escrito a la ligera:
**cada respuesta se valida contra su XSD antes de usarse**, con `lxml`.

```python
c.pedir("auth", "/api/v1/auth/login", xsd="sesion.xsd", ...)
```

Si la respuesta no cumple el esquema, el cliente **no la muestra**: lanza
`ErrorCliente` y la pantalla lo explica.

La alternativa —confiar y leer los campos que uno espera— falla de la peor
manera posible: un campo que cambió de nombre o de tipo produce un `None`
silencioso que se pinta como un dato vacío en la pantalla. El usuario ve
una tabla con huecos y no hay nada en ningún log. Con validación, el
fallo ocurre en el momento y con nombre.

Hay una prueba que lo fija: *una respuesta que no cumple su contrato no se
muestra*.

---

## 6. Qué hace el escritorio cuando algo falla

| Situación | Qué hace |
|---|---|
| Sin conexión | Lo dice y **explica qué hacer**, no muestra una traza |
| Respuesta que no cumple el XSD | No la muestra; error con nombre |
| 401 / token vencido | Renueva con el token de refresco; si tampoco, pide entrar de nuevo |
| 403 | Dice que ese perfil no tiene el permiso, no «error» |
| Cerrar sesión con la red caída | **Borra las credenciales locales igual** |

Ese último merece explicación. Si cerrar sesión dependiera de que el
servicio conteste, un usuario sin red se quedaría con el token guardado en
su máquina creyendo que salió. El cierre local es incondicional; el aviso
al servidor es el que puede fallar. Hay una prueba:
`test_cerrar_sesion_borra_las_credenciales_aunque_falle_la_red`.

---

## 7. La rotación del token de refresco

Al renovar, **cambian los dos**: el de acceso y el de refresco. El cliente
guarda el nuevo de refresco.

Si no lo guardara, la siguiente renovación fallaría — y fallaría quince
minutos después, lejos del código que causó el problema. Hay una prueba
que lo fija (`test_el_ciclo_de_sesion_completo`).

---

## 8. Los permisos no viajan en el token

El cliente los **consulta** al servicio. Si viajaran dentro del JWT,
revocar un permiso no tendría efecto hasta que el token expirara.

Prueba: `test_los_permisos_no_viajan_en_el_token` decodifica la carga del
JWT, comprueba que **no** haya una lista de permisos, y comprueba que aun
así el cliente los tiene — porque los pidió.

---

## 9. Cómo se abre

```
cd codigo
python apps/escritorio/app.py
```

Apunta a donde haga falta **por configuración**, una variable de ambiente
por servicio:

```
AUTH_SERVICE_URL=https://34.41.26.94.sslip.io/auth
DOCUMENTS_SERVICE_URL=https://34.41.26.94.sslip.io/documentos
...
```

Sin tocar código. Cuenta de prueba: `mariana.solis@nexum.com.mx` /
`demo123` (especialista).

Requiere Tkinter. En un intérprete sin Tkinter las pruebas de interfaz se
omiten **y lo dicen**; las del cliente XML corren igual, porque el cliente
no depende de la interfaz.
