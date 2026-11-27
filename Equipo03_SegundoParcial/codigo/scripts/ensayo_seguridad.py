#!/usr/bin/env python3
"""Ensayo automatizado de seguridad, tokens, RBAC, datos invalidos y salud Node.

Disenado para los ensayos en vivo de Integrante 2 (Integrante 2 Sanchez ).
Incluye guarda explicita para NUNCA ejecutar la prueba de 5 fallos contra
cuentas de demostracion reales (como carlos.ramirez@nexum.com.mx).
"""
import argparse
import json
import sys
import urllib.error
import urllib.request

CUENTAS_DEMO_PROTEGIDAS = {
    "carlos.ramirez@nexum.com.mx",
    "ana.perez@nexum.com.mx",
    "lucia.hernandez@nexum.com.mx",
    "mariana.solis@nexum.com.mx",
    "roberto.garcia@nexum.com.mx",
}

SERVICIOS_NODE = {
    "catalog-service": 8103,
    "main-process-service": 8104,
    "survey-service": 8112,
    "indicators-service": 8113,
    "support-service": 8116,
    "organizational-service": 8117,
}


def peticion(metodo: str, url: str, cuerpo=None, headers=None, crudo=None):
    hdrs = dict(headers or {})
    data = crudo
    if cuerpo is not None:
        data = json.dumps(cuerpo).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=hdrs, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def ejecutar_ensayo(args):
    auth = args.auth_url.rstrip("/")
    host_base = args.host_base.rstrip("/")
    print("=== ENSAYO DE SEGURIDAD Y MICROSERVICIOS NODE (INTEGRANTE 2) ===")

    # 1. Salud de los 6 servicios Node
    print("\n[1/6] Verificando /health/ready en los 6 servicios Node.js...")
    for nombre, puerto in SERVICIOS_NODE.items():
        st, txt = peticion("GET", f"{host_base}:{puerto}/health/ready")
        assert st == 200, f"{nombre} ({puerto}) devolvio {st}: {txt}"
        data = json.loads(txt)
        print(f"  - {nombre} (:{puerto}): {st} {data.get('estado')} v={data.get('version_desplegada')}")

    # 2. Login correcto con colaborador de demo
    print("\n[2/6] Probando login valido (ana.perez@nexum.com.mx)...")
    st, txt = peticion("POST", f"{auth}/api/v1/auth/login",
                       {"correo": "ana.perez@nexum.com.mx", "contrasena": args.demo_pass})
    assert st == 200, f"Login valido fallo: {st} {txt}"
    ses = json.loads(txt)
    tok_colab = ses["token_acceso"]
    ref_colab = ses["token_renovacion"]
    print(f"  - Login correcto: {st} (token_acceso + token_renovacion emitidos)")

    # 3. Intento sin permiso (403) y datos mal formados (XXE 400 + D-01 400/422)
    print("\n[3/6] Probando rechazo sin permiso (403) y datos mal formados (XXE / D-01)...")
    st_403, txt_403 = peticion(
        "POST",
        f"{host_base}:8103/api/v1/catalogos/unidades",
        {"nombre": "Unidad Sin Permiso"},
        headers={"Authorization": f"Bearer {tok_colab}"},
    )
    assert st_403 == 403, f"Esperado 403 en catalog-service, obtuvo {st_403}: {txt_403}"
    print(f"  - Sin permiso en catalog-service (:8103): {st_403}")

    xxe = b'<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe "pwn">]><unidad><nombre>&xxe;</nombre></unidad>'
    st_xxe, _ = peticion(
        "POST",
        f"{host_base}:8117/api/v1/organizacion/unidades",
        headers={"Authorization": f"Bearer {tok_colab}", "Content-Type": "application/xml"},
        crudo=xxe,
    )
    assert st_xxe == 400, f"Esperado 400 Anti-XXE en organizational-service, obtuvo {st_xxe}"
    print(f"  - Payload XML malicioso XXE (:8117): {st_xxe}")

    st_d01, _ = peticion(
        "POST",
        f"{host_base}:8104/api/v1/encuestas/respuestas",
        {"campania_id": "CAMP-2026-S1", "empleado_id": "EMP-PROHIBIDO", "valores": []},
        headers={"Authorization": f"Bearer {tok_colab}"},
    )
    assert st_d01 in (400, 422), f"Esperado 400/422 regla D-01, obtuvo {st_d01}"
    print(f"  - Regla D-01 (empleado_id prohibido en :8104): {st_d01}")

    # 4. Renovacion (rotacion) y revocacion inmediata Python -> Node
    print("\n[4/6] Probando renovacion de token y revocacion inmediata Python -> Node...")
    st_ren, txt_ren = peticion("POST", f"{auth}/api/v1/auth/renovar", {"token_renovacion": ref_colab})
    assert st_ren == 200, f"Renovar fallo: {st_ren} {txt_ren}"
    tok_nuevo = json.loads(txt_ren)["token_acceso"]
    print(f"  - Renovar token (:8101): {st_ren}")

    st_out, _ = peticion(
        "POST",
        f"{auth}/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {tok_nuevo}"},
    )
    assert st_out == 200, f"Logout fallo: {st_out}"
    st_rev, _ = peticion(
        "GET",
        f"{host_base}:8103/api/v1/catalogos/unidades?tamano=1",
        headers={"Authorization": f"Bearer {tok_nuevo}"},
    )
    assert st_rev == 401, f"Token revocado debia dar 401 en Node (:8103), obtuvo {st_rev}"
    print(f"  - Logout (:8101) -> rechazo inmediato en catalog-service (:8103): {st_rev}")

    # 5. Login rechazado + bloqueo de 15 min usando cuenta NO real
    correo_bloqueo = args.correo_bloqueo.strip().lower()
    if correo_bloqueo in CUENTAS_DEMO_PROTEGIDAS:
        raise SystemExit(
            f"ABORTADO: '{correo_bloqueo}' es una cuenta demo protegida. "
            "Usa una cuenta ficticia (ej. prueba.bloqueo@nexum.com.mx)."
        )
    print(f"\n[5/6] Probando 5 intentos fallidos y bloqueo de 15 min con '{correo_bloqueo}'...")
    ultimo = 0
    for intento in range(1, 7):
        st_f, _ = peticion("POST", f"{auth}/api/v1/auth/login",
                           {"correo": correo_bloqueo, "contrasena": f"clave_mala_{intento}"})
        ultimo = st_f
        print(f"  - Intento {intento}: HTTP {st_f}")
        if st_f == 429:
            break
    assert ultimo == 429, f"Esperado bloqueo 429 tras intentos fallidos, obtuvo {ultimo}"

    # 6. Portal web opcional
    if args.web_url:
        print(f"\n[6/6] Verificando acceso publico al portal ({args.web_url.rstrip('/')}/entrar)...")
        st_w, _ = peticion("GET", f"{args.web_url.rstrip('/')}/entrar")
        assert st_w == 200, f"Portal /entrar respondio {st_w}"
        print(f"  - Portal /entrar: HTTP {st_w}")
    else:
        print("\n[6/6] Portal web omitido (pasa --web-url para validarlo tambien).")

    print("\n[OK] Ensayo de seguridad de Integrante 2 completado sin bloquear cuentas reales.")


def main():
    parser = argparse.ArgumentParser(
        description="Ensayo automatizado de seguridad, tokens y servicios Node (Integrante 2)."
    )
    parser.add_argument("--auth-url", default="http://127.0.0.1:8101",
                        help="URL base de auth-service (defecto http://127.0.0.1:8101)")
    parser.add_argument("--host-base", default="http://127.0.0.1",
                        help="Host base donde escuchan los puertos Node 8103..8117")
    parser.add_argument("--web-url", default="",
                        help="URL opcional del portal web (ej. http://localhost:8000 o https://34.41.26.94.sslip.io)")
    parser.add_argument("--demo-pass", default="demo123",
                        help="Contrasena de demo para ana.perez (defecto demo123)")
    parser.add_argument("--correo-bloqueo", default="prueba.bloqueo@nexum.com.mx",
                        help="Correo ficticio para la prueba de bloqueo de 5 intentos")
    args = parser.parse_args()
    ejecutar_ensayo(args)


if __name__ == "__main__":
    try:
        main()
    except AssertionError as exc:
        print(f"[FALLO] {exc}", file=sys.stderr)
        sys.exit(1)
