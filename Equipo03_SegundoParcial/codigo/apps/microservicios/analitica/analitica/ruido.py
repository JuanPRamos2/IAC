"""
Lo que el ruido de Laplace permite y lo que impide.

POR QUÉ ESTE MÓDULO VA PRIMERO
-------------------------------
Todo lo que este paquete analiza son valores que **ya llevan ruido**. El
sistema los publicó aplicando el mecanismo de Laplace, así que cada número
que llega aquí es el valor real más una perturbación aleatoria.

Un detector de anomalías que ignore eso marca ruido como hallazgo. Y no es
un error que se vea: produce una lista de unidades «en riesgo» con aspecto
perfectamente creíble, se interviene sobre un equipo al que no le pasaba
nada, y nadie se entera de que la señal nunca existió.

Así que la pregunta que resuelve este módulo no es «¿cuánto se desvía esta
unidad?» sino **«¿cuánto tendría que desviarse para que el ruido no lo
explique?»**. Como el sistema guarda la escala del ruido que aplicó
(`agregado.resultado_protegido.escala_ruido`), esa pregunta tiene
respuesta exacta en lugar de un umbral inventado.

EL MECANISMO, EN UNA FRASE
---------------------------
Al publicar un promedio de una unidad se le suma una muestra de
Laplace(0, b), con b = sensibilidad / epsilon. La densidad es

    f(x) = (1 / 2b) · exp(-|x| / b)

y lo único que hace falta de ella es la cola: la probabilidad de que el
ruido solo, por azar, produzca una desviación de al menos t.
"""
import math

# Dos muestras independientes de Laplace(0, b) se restan al comparar dos
# valores publicados. La diferencia no es Laplace, pero su desviación
# estándar sí se conoce: cada muestra aporta varianza 2b², así que la
# diferencia tiene varianza 4b² y desviación 2b.
#
# Se usa sqrt(2) como factor sobre una sola escala —y no 2— cuando se
# compara un valor contra un centroide calculado de MUCHOS valores: el
# ruido del centroide se promedia y casi desaparece, así que la varianza
# de la comparación la domina el ruido del valor suelto.
FACTOR_DOS_MUESTRAS = 2.0
FACTOR_CONTRA_CENTROIDE = math.sqrt(2.0)


def cola_laplace(t, b):
    """P(|X| >= t) para X ~ Laplace(0, b).

    Es exp(-t/b), y sale de integrar la densidad desde t hasta infinito y
    doblarla por simetría. Esta es la probabilidad de que el ruido SOLO
    produzca una desviación tan grande como la observada.

    Con b = 0 —sin ruido aplicado— cualquier desviación distinta de cero
    es imposible por azar, así que devuelve 0. Importa tratarlo aparte:
    dividir entre cero aquí daría una excepción en mitad de un análisis
    que por lo demás es correcto.
    """
    if b is None or b <= 0:
        return 0.0 if t > 0 else 1.0
    if t <= 0:
        return 1.0
    return math.exp(-t / b)


def umbral_para_confianza(b, confianza=0.95, factor=FACTOR_CONTRA_CENTROIDE):
    """Desviación mínima para afirmar algo con esa confianza.

    Es el inverso de la cola: t = -b · ln(1 - confianza). Con b = 0.5 y
    confianza 0.95 da 1.498, es decir que una unidad tiene que estar a
    casi punto y medio de sus pares antes de que el ruido deje de ser una
    explicación suficiente.

    Ese número parece severo y lo es a propósito. El coste de los dos
    errores no es simétrico: marcar una unidad sana desgasta la confianza
    del programa entero —la gente deja de contestar cuando cree que la
    herramienta inventa problemas—, mientras que no marcar una unidad que
    sí tiene un problema solo retrasa una intervención que la siguiente
    campaña volverá a sugerir.
    """
    if b is None or b <= 0:
        return 0.0
    if not 0 < confianza < 1:
        raise ValueError("la confianza va entre 0 y 1, sin incluirlos")
    return factor * b * -math.log(1.0 - confianza)


def significancia(desviacion, b, factor=FACTOR_CONTRA_CENTROIDE):
    """Qué tan improbable es que el ruido explique esta desviación.

    Devuelve (p, supera) con p = P(ruido >= |desviacion|). Un p pequeño
    dice que el ruido es mala explicación; NO dice que la causa sea un
    problema de bienestar, y esa distinción se arrastra hasta la salida
    del motor para que nadie la pierda por el camino.
    """
    t = abs(desviacion)
    escala = (b or 0.0) * factor
    p = cola_laplace(t, escala)
    return p, p < 0.05


def escala_combinada(escalas):
    """La escala que gobierna una comparación entre varios valores.

    Se toma la mayor y no el promedio: una comparación es tan incierta
    como su término más ruidoso. Promediarlas haría parecer fiable una
    comparación en la que uno de los dos lados apenas se puede leer.
    """
    utiles = [float(e) for e in escalas if e is not None and float(e) > 0]
    return max(utiles) if utiles else 0.0
