"""
Carga contra el PORTAL PÚBLICO, por HTTPS, como la vive una persona.

POR QUÉ HAY DOS ARCHIVOS DE CARGA Y NO UNO
------------------------------------------
`locustfile.py` mide los **microservicios**: entra por `auth-service`,
pide agregados a `queries-service`, corre el análisis en
`algorithms-service`. Eso mide la capacidad del sistema.

Y no se puede correr desde internet, porque **los microservicios no están
expuestos**. Caddy publica un solo destino:

    34.41.26.94.sslip.io  ->  127.0.0.1:8000   (el portal)

Eso es correcto y deliberado: es la misma decisión por la que el puerto de
la base no se publica. Exponer veinticuatro microservicios al mundo para
poder medirlos sería cambiar la postura de seguridad del sistema para
facilitar una prueba.

Así que son dos mediciones distintas y las dos hacen falta:

| Archivo | Dónde se corre | Qué mide |
|---|---|---|
| `locustfile.py` | **en la máquina virtual** | los microservicios, con recursos de la nube |
| `locustfile_portal.py` | **desde donde sea** | el camino real del usuario: DNS, TLS, Caddy, portal |

Esta segunda es la que de verdad contesta «¿cómo se siente el sistema
desde afuera?», porque incluye el saludo TLS y el proxy inverso, que la
primera no toca. Y es la que corresponde literalmente a «correr Locust
contra https://34.41.26.94.sslip.io».

CÓMO SE CORRE
-------------
    locust -f pruebas/carga/locustfile_portal.py \
           --host https://34.41.26.94.sslip.io \
           --headless -u 40 -r 2 -t 3m \
           --csv informes/portal_nube

QUÉ *NO* HACE, Y POR QUÉ
------------------------
No contesta encuestas ni escribe nada. Una prueba de carga que escribe
deja basura en la base de la demostración, y además mediría el camino de
escritura de una campaña real. Aquí se navega: entrar, el portal, el
consentimiento, los accesos, las notificaciones. Es lo que hace la mayoría
de la gente la mayoría del tiempo.
"""
import os
import random

from locust import HttpUser, between, task

# Las mismas cuentas de demostración. Con pocas personas virtuales no hace
# falta el banco de 166 cuentas de carga: el limitador es de 120 peticiones
# por minuto y por token, y con esperas de persona no se alcanza.
CUENTAS = [
    ("ana.perez@nexum.com.mx", "demo123"),
    ("lucia.hernandez@nexum.com.mx", "demo123"),
    ("mariana.solis@nexum.com.mx", "demo123"),
]

VERIFICAR_TLS = os.environ.get("NEXUM_TLS_VERIFICAR", "1") != "0"


class PersonaEnElPortal(HttpUser):
    """Una persona que entra al portal y mira sus cosas."""

    # Esperas de persona, no de robot. Sin esto se mide el limitador.
    wait_time = between(3, 12)

    def on_start(self):
        self.client.verify = VERIFICAR_TLS
        correo, clave = random.choice(CUENTAS)
        with self.client.post(
                "/entrar",
                data={"correo": correo, "contrasena": clave},
                name="POST /entrar",
                allow_redirects=True,
                catch_response=True) as r:
            # El portal contesta 200 con la página siguiente tras redirigir.
            # Un 200 que en realidad es la pantalla de login otra vez NO es
            # un éxito, y contarlo como tal haría que toda la corrida
            # midiera peticiones de alguien que nunca entró.
            if r.status_code == 200 and "entrar" not in r.url:
                r.success()
            else:
                r.failure(f"no entro: {r.status_code} {r.url}")

    @task(5)
    def portal(self):
        self.client.get("/portal/", name="GET /portal/")

    @task(3)
    def notificaciones(self):
        self.client.get("/notificaciones/", name="GET /notificaciones/")

    @task(2)
    def consentimiento(self):
        self.client.get("/portal/consentimiento",
                        name="GET /portal/consentimiento")

    @task(2)
    def mis_accesos(self):
        self.client.get("/portal/mis-accesos", name="GET /portal/mis-accesos")

    @task(1)
    def salud(self):
        # Barata a propósito: sirve de línea base. Si ésta se degrada, el
        # problema es de la máquina o del proxy, no de una consulta.
        self.client.get("/salud", name="GET /salud")
