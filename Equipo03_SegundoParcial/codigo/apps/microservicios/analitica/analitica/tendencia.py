"""
Tendencia de una serie corta y ruidosa: Theil–Sen y Mann–Kendall.

POR QUÉ NO MÍNIMOS CUADRADOS
-----------------------------
La regresión lineal por mínimos cuadrados es lo que todo el mundo usa y
aquí sería un error. Dos motivos, y el segundo es el grave:

1. Las series tienen entre tres y diez puntos —una por campaña—, y con
   tan pocos un solo valor atípico arrastra la pendiente entera.

2. Esos valores llevan ruido de Laplace, que tiene **colas pesadas**: a
   diferencia de una normal, produce valores lejanos con una frecuencia
   que no es despreciable. Mínimos cuadrados minimiza el error al
   cuadrado, así que cada punto lejano pesa por su distancia elevada al
   cuadrado. Es el peor método posible para exactamente estos datos.

Theil–Sen toma la MEDIANA de las pendientes entre todos los pares de
puntos. Aguanta hasta un 29% de puntos corrompidos antes de romperse, y
con series de este tamaño y este ruido eso es justo lo que hace falta.

POR QUÉ ADEMÁS MANN–KENDALL
----------------------------
Theil–Sen da una pendiente, pero no dice si esa pendiente significa algo.
Una serie puramente aleatoria también tiene pendiente; casi nunca es
cero exacto. Mann–Kendall contesta la otra mitad: cuenta cuántos pares
van hacia arriba y cuántos hacia abajo y compara ese desbalance con el
que produciría el azar.

Las dos cosas juntas permiten decir «baja 0.18 por campaña, y el azar no
lo explica», que es lo que se puede llevar a un comité. Solo con la
pendiente se diría «baja 0.18» sin saber si bajar 0.18 es noticia.

COMPLEJIDAD
-----------
Los dos recorren todos los pares: O(m²) con m puntos de la serie. Con m
pequeño —campañas de un semestre— eso es trivial, y la alternativa O(m
log m) no compensa la pérdida de claridad.
"""
import math

# Con menos de tres puntos no hay tendencia que calcular: dos valores
# cualesquiera definen una recta perfecta, y esa recta no dice nada.
MINIMO_PUNTOS = 3


def _mediana(valores):
    if not valores:
        return None
    s = sorted(valores)
    n = len(s)
    medio = n // 2
    return s[medio] if n % 2 else (s[medio - 1] + s[medio]) / 2.0


def theil_sen(x, y):
    """Pendiente robusta: la mediana de las pendientes entre pares.

    Devuelve (pendiente, interseccion). La intersección se calcula como
    la mediana de (y_i - pendiente·x_i), que es la versión robusta que
    corresponde a una pendiente robusta: usar la media ahí reintroduciría
    la sensibilidad a los valores lejanos que la pendiente acaba de
    quitar.
    """
    n = len(x)
    if n < 2:
        return 0.0, (y[0] if y else 0.0)
    pendientes = [(y[j] - y[i]) / (x[j] - x[i])
                  for i in range(n) for j in range(i + 1, n)
                  if x[j] != x[i]]
    if not pendientes:
        return 0.0, _mediana(y) or 0.0
    pendiente = _mediana(pendientes)
    interseccion = _mediana([yi - pendiente * xi for xi, yi in zip(x, y)])
    return pendiente, interseccion


def mann_kendall(y):
    """¿El azar explica esta tendencia? Devuelve (S, z, p, direccion).

    S cuenta los pares crecientes menos los decrecientes. Bajo la
    hipótesis de que no hay tendencia, S tiene media 0 y varianza
    conocida, así que se normaliza a z y de ahí sale p.

    La corrección por continuidad (restar 1 a |S|) importa con series
    cortas: sin ella, p sale optimista y se declaran tendencias que no
    están.
    """
    n = len(y)
    if n < MINIMO_PUNTOS:
        return 0, 0.0, 1.0, "INDETERMINADA"

    s = 0
    for i in range(n - 1):
        for j in range(i + 1, n):
            if y[j] > y[i]:
                s += 1
            elif y[j] < y[i]:
                s -= 1

    # Varianza con corrección por empates: un grupo de g valores iguales
    # aporta menos información y la fórmula lo descuenta. Con valores
    # continuos casi no hay empates, pero los valores publicados vienen
    # redondeados a tres decimales y sí los producen.
    conteos = {}
    for valor in y:
        conteos[valor] = conteos.get(valor, 0) + 1
    empates = sum(g * (g - 1) * (2 * g + 5) for g in conteos.values() if g > 1)
    varianza = (n * (n - 1) * (2 * n + 5) - empates) / 18.0
    if varianza <= 0:
        return s, 0.0, 1.0, "ESTABLE"

    if s > 0:
        z = (s - 1) / math.sqrt(varianza)
    elif s < 0:
        z = (s + 1) / math.sqrt(varianza)
    else:
        z = 0.0

    # p a dos colas desde la normal estándar. math.erfc evita tener que
    # traer scipy solo por esto, y el proyecto no tiene esa dependencia.
    p = math.erfc(abs(z) / math.sqrt(2.0))

    if p >= 0.05:
        direccion = "ESTABLE"
    elif s > 0:
        direccion = "AL_ALZA"
    else:
        direccion = "A_LA_BAJA"
    return s, z, p, direccion


def analizar(puntos):
    """Analiza una serie de (secuencia, valor, escala_ruido).

    Los puntos sin valor —suprimidos por el umbral k— se DESCARTAN del
    cálculo pero se cuentan y se reportan. Lo que no se puede hacer es
    tratarlos como si la serie fuera continua: si una unidad no publicó
    en la campaña 3, las campañas 2 y 4 no son consecutivas, y el salto
    entre ellas no es un paso sino dos.

    Por eso la pendiente se calcula contra la SECUENCIA real de campaña y
    no contra la posición en la lista. Esa distinción es la que convierte
    «bajó 0.4 entre dos lecturas» en «bajó 0.2 por campaña».
    """
    publicados = [(s, v, e) for s, v, e in puntos if v is not None]
    suprimidos = len(puntos) - len(publicados)

    if len(publicados) < MINIMO_PUNTOS:
        return {
            "puntos_publicados": len(publicados),
            "puntos_suprimidos": suprimidos,
            "direccion": "INDETERMINADA",
            "pendiente_por_campania": None,
            "p_valor": None,
            "lectura": f"Solo {len(publicados)} campanias publicadas. Hacen "
                       f"falta {MINIMO_PUNTOS} para hablar de tendencia: con "
                       f"dos puntos, cualquier par de valores define una recta "
                       f"perfecta que puede ser enteramente azar.",
        }

    x = [float(s) for s, _, _ in publicados]
    y = [float(v) for _, v, _ in publicados]
    pendiente, interseccion = theil_sen(x, y)
    s, z, p, direccion = mann_kendall(y)

    # El tamaño del cambio se compara con el ruido: una pendiente real
    # pero diminuta frente al ruido no sostiene una decisión.
    from .ruido import escala_combinada, FACTOR_DOS_MUESTRAS
    escala = escala_combinada([e for _, _, e in publicados])
    recorrido = abs(pendiente) * (max(x) - min(x))
    supera_ruido = recorrido > FACTOR_DOS_MUESTRAS * escala

    if direccion == "INDETERMINADA":
        lectura = "No hay suficientes campanias publicadas."
    elif direccion == "ESTABLE":
        lectura = (f"Sin tendencia distinguible del azar (p={p:.3f}). No "
                   f"significa que no haya cambiado nada: significa que si "
                   f"cambio, no se puede separar del ruido.")
    else:
        hacia = "a la baja" if direccion == "A_LA_BAJA" else "al alza"
        lectura = (f"Tendencia {hacia} de {abs(pendiente):.3f} por campania "
                   f"(p={p:.3f}). Recorrido total {recorrido:.3f} frente a un "
                   f"ruido de {FACTOR_DOS_MUESTRAS * escala:.3f}: "
                   f"{'lo supera' if supera_ruido else 'NO lo supera, asi que '
                      'la direccion es creible pero la magnitud no'}.")

    return {
        "puntos_publicados": len(publicados),
        "puntos_suprimidos": suprimidos,
        "direccion": direccion,
        "pendiente_por_campania": round(pendiente, 4),
        "interseccion": round(interseccion, 4),
        "estadistico_s": s,
        "z": round(z, 4),
        "p_valor": round(p, 4),
        "recorrido_total": round(recorrido, 4),
        "umbral_de_ruido": round(FACTOR_DOS_MUESTRAS * escala, 4),
        "supera_el_ruido": supera_ruido,
        "lectura": lectura,
    }
