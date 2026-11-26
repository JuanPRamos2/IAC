# Contenedor propio de algorithms-service.
# El contexto de build es apps/microservicios/ para poder copiar la
# libreria comun, que los cuatro servicios comparten.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY comun /tmp/comun
RUN pip install --no-cache-dir /tmp/comun && rm -rf /tmp/comun

# `analitica` es el paquete del análisis complejo: agrupamiento,
# calibración contra el ruido de privacidad y estimación de tendencia.
# Va instalado como librería y no copiado dentro del servicio porque el
# conjunto de pruebas lo ejerce por separado, sin levantar Flask ni
# PostgreSQL: un algoritmo que solo se puede probar a través de un
# endpoint no se puede probar.
#
# No arrastra numpy ni scipy, a propósito. Son veinte veces el tamaño de
# la imagen para usar media docena de funciones, y aquí cada línea de la
# matemática —el mecanismo de Laplace, la pendiente de Theil-Sen, la
# corrección de empates de Mann-Kendall— está escrita y comentada donde
# se puede leer y defender.
COPY analitica /tmp/analitica
RUN pip install --no-cache-dir /tmp/analitica && rm -rf /tmp/analitica

COPY algorithms-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY algorithms-service/ .

RUN useradd --create-home --shell /usr/sbin/nologin servicio && chown -R servicio /app
USER servicio

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/live',timeout=2).status==200 else 1)"

# --timeout 30 es la ULTIMA red, no el limite de verdad.
#
# El limite que importa esta en el codigo: statement_timeout de 15 s en
# PostgreSQL (comun/datos.py) y un plazo de 20 s por peticion
# (comun/servicio.py). Los dos contestan un 503 con codigo, mensaje y
# que hacer. Este tope, en cambio, mata al obrero: el cliente recibe una
# conexion cortada sin codigo ni identificador de correlacion, la consulta
# sigue viva en PostgreSQL, y se cae lo que ese obrero tenia en vuelo.
#
# Por eso esta POR ENCIMA de los otros dos, y el orden es la decision: si
# este actuara primero, los dos limites buenos no se verian nunca y el
# cliente seguiria sin saber que paso.
CMD ["gunicorn","-b","0.0.0.0:8000","-w","2","-k","gthread","--threads","2","--timeout","30","--graceful-timeout","10","--access-logfile","-","app:app"]
