package mx.com.nexum.bienestar.datos

import mx.com.nexum.bienestar.BuildConfig
import mx.com.nexum.bienestar.red.ClienteApi
import mx.com.nexum.bienestar.red.objetos
import org.json.JSONArray
import org.json.JSONObject

data class Campania(
    val campaniaId: String,
    val nombre: String,
    val instrumentoId: String,
    val versionInstrumento: Int,
    val estado: String,
    val fechaInicio: String,
    val fechaFin: String,
) {
    val estaAbierta: Boolean get() = estado == "ABIERTA"
}

data class Reactivo(
    val reactivoId: String,
    val texto: String,
    val dimensionId: String,
    val orden: Int,
    val invertido: Boolean,
)

data class Aviso(
    val avisoId: String,
    val titulo: String,
    val cuerpo: String,
    val fecha: String,
    val leido: Boolean,
)

/**
 * Catálogo: campañas e instrumento con sus reactivos.
 *
 * Las preguntas NO están escritas en la aplicación. Vienen del catálogo, con
 * su versión. Si estuvieran en el código, cambiar una pregunta obligaría a
 * publicar una versión nueva en la tienda y a esperar a que la gente la
 * instale; mientras tanto, dos personas estarían contestando instrumentos
 * distintos bajo la misma campaña y los agregados mezclarían ambos.
 */
class CatalogoRepositorio(
    private val api: ClienteApi,
    private val url: String = BuildConfig.URL_CATALOGOS,
) {
    suspend fun campanias(): List<Campania> {
        val respuesta = api.obtener("$url/api/v1/catalogos/campanias?limit=20")
        return respuesta.optJSONArray("campanias").objetos().map {
            Campania(
                campaniaId = it.getString("campania_id"),
                nombre = it.optString("nombre"),
                instrumentoId = it.optString("instrumento_id"),
                versionInstrumento = it.optInt("version_instrumento", 1),
                estado = it.optString("estado"),
                fechaInicio = it.optString("fecha_inicio"),
                fechaFin = it.optString("fecha_fin"),
            )
        }
    }

    /** La campaña abierta, o null si no hay ninguna ahora mismo. */
    suspend fun campaniaAbierta(): Campania? = campanias().firstOrNull { it.estaAbierta }

    suspend fun reactivosDe(campania: Campania): List<Reactivo> {
        val respuesta = api.obtener(
            "$url/api/v1/catalogos/instrumentos/${campania.instrumentoId}" +
                "/versiones/${campania.versionInstrumento}/reactivos"
        )
        val arreglo: JSONArray = respuesta.optJSONArray("reactivos")
            ?: respuesta.optJSONArray("elementos")
            ?: JSONArray()
        return arreglo.objetos().map {
            Reactivo(
                reactivoId = it.getString("reactivo_id"),
                texto = it.optString("texto"),
                dimensionId = it.optString("dimension_id"),
                orden = it.optInt("orden", 0),
                invertido = it.optBoolean("invertido", false),
            )
        }.sortedBy { it.orden }
    }
}

/**
 * Proceso: responder la encuesta y consultar la participación propia.
 *
 * QUÉ DEVUELVE «MIS RESPUESTAS», Y QUÉ NO
 * ---------------------------------------
 * Devuelve que participaste y cuándo, no QUÉ contestaste. No es una
 * limitación de la pantalla: el servidor no puede recuperarlo. Las
 * respuestas se guardan bajo seudónimo y la relación entre la persona y el
 * seudónimo no permite ir de vuelta. Si la aplicación pudiera mostrar tus
 * respuestas, cualquiera con tu teléfono desbloqueado también podría, y la
 * promesa del sistema dejaría de ser cierta.
 */
class EncuestaRepositorio(
    private val api: ClienteApi,
    private val url: String = BuildConfig.URL_PROCESO,
) {
    suspend fun enviarRespuestas(
        campaniaId: String,
        respuestas: Map<String, Int>,
    ): JSONObject {
        // `valores`, y como OBJETO { reactivo_id: valor }.
        //
        // EL DEFECTO QUE ESTO CORRIGE
        // La aplicacion mandaba la clave `respuestas` con un ARREGLO de
        // objetos `{reactivo_id, valor}`. El servicio espera `valores` como
        // un objeto, y rechazaba el envio con:
        //
        //   PARAMETRO_INVALIDO
        //   'valores' debe ser un objeto { reactivo_id: valor }.
        //
        // Es decir: la encuesta NUNCA se pudo enviar desde el telefono.
        // Entraba, cargaba los reactivos, dejaba contestar las cinco, y
        // fallaba en el ultimo paso. Solo se ve ejecutando la aplicacion
        // contra el servicio: ninguna prueba del lado movil lo habria
        // encontrado, porque el formato que armaba era valido como JSON.
        //
        // Manda el servicio y no la aplicacion porque la forma del cuerpo
        // es parte del contrato publicado, y el portal web y el servicio
        // de proceso ya la usan asi (`Object.keys(d.valores)`).
        val valores = JSONObject()
        respuestas.forEach { (reactivoId, valor) -> valores.put(reactivoId, valor) }
        val cuerpo = JSONObject()
            .put("campania_id", campaniaId)
            .put("valores", valores)
        // Nótese lo que NO se manda: ningún identificador de empleado. El
        // servicio lo rechazaría (regla D-01), y mandarlo sería pedirle al
        // servidor que rompiera su propia garantía.
        return api.publicar("$url/api/v1/encuestas/respuestas", cuerpo)
    }

    suspend fun participacionPropia(): JSONObject =
        api.obtener("$url/api/v1/encuestas/respuestas/propias")
}

/** Solicitudes de apoyo levantadas desde el teléfono. */
class ApoyoRepositorio(
    private val api: ClienteApi,
    private val url: String = BuildConfig.URL_PROCESO,
) {
    suspend fun pedirApoyo(mensaje: String): JSONObject =
        api.publicar(
            "$url/api/v1/solicitudes-apoyo",
            JSONObject().put("mensaje", mensaje.trim()),
        )
}

/** Avisos dirigidos a la persona. */
class AvisosRepositorio(
    private val api: ClienteApi,
    private val url: String = BuildConfig.URL_NOTIFICACIONES,
) {
    suspend fun mios(): List<Aviso> {
        val respuesta = api.obtener("$url/api/v1/notificaciones/mias?tamano=30")
        val arreglo = respuesta.optJSONArray("notificaciones")
            ?: respuesta.optJSONArray("elementos")
            ?: JSONArray()
        return arreglo.objetos().map {
            Aviso(
                avisoId = it.optString("notificacion_id", it.optString("id")),
                titulo = it.optString("titulo"),
                cuerpo = it.optString("cuerpo", it.optString("mensaje")),
                fecha = it.optString("fecha", it.optString("fecha_envio")),
                leido = it.optBoolean("leido", false),
            )
        }
    }

    suspend fun sinLeer(): Int =
        api.obtener("$url/api/v1/notificaciones/sin-leer").optInt("total", 0)
}
