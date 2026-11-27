# Manual de usuario

**Expediente NEXUM — Equipo 03 · Capítulo de Gerardo Quiroga Ramírez
(#650313)**

Una página por perfil. Cinco perfiles: Colaborador, Líder, Especialista,
Auditor y Administrador.

Entrada: `http://localhost:8000` en la laptop,
`https://34.41.26.94.sslip.io` en la nube. Contraseña de demostración:
`demo123`.

---

## Colaborador — `ana.perez@nexum.com.mx`

**Quién es.** Cualquier persona de la organización. Contesta la encuesta
de bienestar y pide apoyo si lo necesita.

### Qué puede hacer

| | Dónde |
|---|---|
| Contestar la campaña abierta | Portal → *Mi encuesta*; o la app móvil |
| Ver y cambiar su consentimiento | Portal → *Mi consentimiento* |
| Pedir apoyo | Portal → *Solicitar apoyo* |
| Ver sus notificaciones | Portal → *Notificaciones* |

### Lo que NO puede hacer, y por qué

**No ve resultados de su unidad ni de ninguna otra.** No es una limitación
de la interfaz: el permiso `AGREGADO_UNIDAD` no está en su perfil. Si un
colaborador pudiera ver el agregado de su propio equipo de 6 personas,
sabría casi exactamente qué contestaron sus 5 compañeros.

### Si no aparece la encuesta

Puede pasar y **no es un error**. Las campañas se convocan por unidad: si
la unidad de esa persona no fue convocada a la campaña abierta, el portal
lo explica y redirige. (Esto se descubrió escribiendo una prueba que
asumía lo contrario — la prueba estaba mal y el sistema bien.)

### Su consentimiento

Puede **revocarlo** cuando quiera. A partir de ese momento sus respuestas
dejan de contar en los agregados nuevos. Lo que ya se calculó y publicó no
se recalcula: tiene ruido aplicado y recalcularlo con otro ruido sería
peor para su privacidad, no mejor.

---

## Líder — `lucia.hernandez@nexum.com.mx`

**Quién es.** Responsable de una unidad. Ve cómo está su equipo, nunca
quién dijo qué.

### Qué puede hacer

| | Dónde |
|---|---|
| Tablero de su unidad | Portal → *Mi unidad* |
| Serie histórica por campaña | Portal → *Tendencias* |
| Ver las notificaciones de su unidad | Portal → *Notificaciones* |

### Lo que ve, y lo que significa

Los números del tablero **llevan ruido**. Un 3.8 quiere decir «alrededor
de 3.8, con una incertidumbre de ±0.30 puntos». No es un promedio exacto y
no debe tratarse como tal: la diferencia entre 3.8 y 3.9 de una campaña a
otra **no significa nada**.

### Cuando una casilla dice «suprimido»

Significa que ese grupo tiene **menos de 5 personas** con consentimiento
vigente. No es un dato que falte ni un error: es la protección
funcionando. Publicarlo permitiría identificar a esas personas.

**No se puede pedir que se publique.** No hay opción para eso, y es a
propósito.

### Lo que NO puede hacer

Ver el detalle individual, ni comparar a dos personas, ni seguir a una
persona en el tiempo. No existe la consulta, en ningún perfil.

---

## Especialista — `mariana.solis@nexum.com.mx`

**Quién es.** Salud ocupacional o recursos humanos. Analiza, propone
intervenciones y atiende solicitudes de apoyo.

### Qué puede hacer

| | Dónde |
|---|---|
| Análisis de riesgo de toda la organización | Portal → *Análisis* |
| Proponer un plan de intervención | Portal → *Intervenciones* → *Proponer* |
| Cargar evidencia de una sesión | Portal → *Intervenciones* → *Evidencias* |
| Generar reportes de bienestar | Portal → *Reportes* |
| Atender solicitudes de apoyo | Portal → *Apoyo* |
| Lo mismo desde el escritorio | `python apps/escritorio/app.py` |

### Cómo leer el análisis

Cada unidad sale con un nivel:

| Nivel | Qué quiere decir |
|---|---|
| **PRIORITARIO** | dos o más dimensiones anómalas, o tres empeorando |
| **ATENCIÓN** | una anomalía, o dos dimensiones empeorando |
| **INFORMATIVO** | nada que destaque |

El nivel sale de **reglas**, no de un puntaje, para que se pueda explicar
en una frase: *«esta unidad sale PRIORITARIO porque tiene dos dimensiones
anómalas»*. El puntaje sólo ordena dentro de cada nivel.

Una anomalía exige **dos** condiciones: que supere el ruido *y* que sea
materialmente grande. Con datos masivos el ruido baja tanto que todo sale
«significativo»; sin la segunda condición el análisis marcaría decenas de
diferencias de 0.12 puntos que no significan nada.

**Uno de cada seis avisos de deterioro es un falso positivo** (precisión
83.3 %). Está medido y se dice: el análisis abre una conversación con un
equipo, no dispara una acción automática.

### Lo que NO puede hacer

**No puede aprobar su propio plan.** Lo propone, y otra persona con el
mismo permiso lo aprueba. Si lo intenta:

```
APROBACION_DEL_PROPIO_AUTOR
"Pidelo a otra persona con el permiso de aprobar."
```

No es desconfianza: quien detecta la necesidad no es quien autoriza el
cambio. Por eso existe la segunda cuenta de especialista,
`teresa.villalobos@nexum.com.mx`.

### Evidencias

Formatos: PDF, PNG, JPG, DOCX, XLSX, TXT, CSV. Máximo 8 MB.

Un archivo con la extensión cambiada **se rechaza**: el tipo se decide por
el contenido, no por el nombre.

---

## Auditor — `roberto.garcia@nexum.com.mx`

**Quién es.** Verifica que el sistema cumpla, sin poder cambiar nada.

### Qué puede hacer

| | Dónde |
|---|---|
| Consultar la bitácora | Portal → *Auditoría* |
| Descargar evidencia registrada | Portal → *Documentos* |
| Ver el presupuesto de privacidad | Portal → *Gobierno del dato* |
| Ver garantías de privacidad | Portal → *Gobierno del dato* |

### La bitácora

Cada acción deja: quién, qué perfil, qué acción, sobre qué recurso, con
qué resultado y con qué identificador de correlación. El identificador
permite seguir una operación que pasó por tres servicios con un solo
número.

**Incluye los rechazos.** Un intento de aprobar el propio plan queda
registrado como `RECHAZADO`, no desaparece.

### Descargar evidencia

Al abrir un documento, el sistema comprueba que el archivo esté realmente
en el bucket antes de dar la dirección. La dirección **vence a los 10
minutos** y no pide contraseña: es de un solo uso práctico, no un enlace
para reenviar.

Si el archivo cambió después de registrarse, **no se entrega**: se compara
contra el sello que quedó al subirlo.

### Lo que NO puede hacer

Cambiar nada. Ni borrar una fila de la bitácora — la base no se lo
permite al rol de aplicación, así que no es una regla de pantalla.

---

## Administrador — `carlos.ramirez@nexum.com.mx`

**Quién es.** Administra cuentas, perfiles, permisos y parámetros. **No
ve datos de bienestar.**

### Qué puede hacer

| | Dónde |
|---|---|
| Alta, baja y edición de usuarios | Portal → *Administración* → *Usuarios* |
| Asignar perfiles | Portal → *Administración* → *Perfiles* |
| Ver la matriz de permisos | Portal → *Administración* → *Permisos* |
| Parámetros del sistema | Portal → *Administración* → *Parámetros* |
| **Panel de estado de los servicios** | Portal → *Administración* → *Servicios* |

### El panel de servicios

Cuatro estados, y se arreglan en lugares distintos:

| Estado | Qué pasa | Qué hacer |
|---|---|---|
| **Disponible** | todo responde | nada |
| **Degradado** | una dependencia **opcional** caída; atiende igual | mirar `degradado_por`; no es urgente |
| **No listo** | una dependencia **esencial** caída; el proceso vive y dice qué le falta | revisar esa dependencia, no el servicio |
| **Caído** | no contesta | reiniciar el servicio |

Además muestra: última verificación, tiempo, disponibilidad de los últimos
60 minutos con el número de muestras, versión desplegada, dependencias que
no aplican, y los errores de las últimas 24 horas desde la bitácora.

«No aplica» **no es lo mismo que «no se comprobó»**, y por eso se dice: un
servicio que no usa MongoDB lo declara, en lugar de dejar un hueco que
podría ser un fallo de observabilidad.

### Lo que NO puede hacer, y es a propósito

- **No genera reportes de bienestar** → 403.
- **No toca evidencia de intervención** → 403.
- **No aprueba intervenciones** → 403.
- **No se quita a sí mismo la administración**, para que nadie deje el
  sistema sin administradores por accidente.

Los tres 403 son separación de funciones: quien administra las cuentas no
debería poder leer los datos de bienestar de las personas cuyas cuentas
administra.
