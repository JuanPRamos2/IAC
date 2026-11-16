import zipfile
import shutil
import xml.etree.ElementTree as ET
import os

ET.register_namespace('p', 'http://schemas.openxmlformats.org/presentationml/2006/main')
ET.register_namespace('a', 'http://schemas.openxmlformats.org/drawingml/2006/main')
ET.register_namespace('r', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships')

UPDATES = {
    # SLIDE 1
    (1, "TextBox 15", 0): "JUAN PABLO RAMOS · 610248",
    (1, "TextBox 15", 1): "RICARDO ARATH SÁNCHEZ AGUIRRE · 583928",
    (1, "TextBox 18", 0): "Arquitectura de Microservicios · Parcial 2",

    # SLIDE 2
    (2, "TextBox 26", 0): "Bienestar Nexum · UDEM",
    (2, "TextBox 22", 0): "Entrega 2: plataforma distribuida con microservicios desacoplados, persistencia políglota y contratos duales JSON/XML.",
    (2, "TextBox 23", 0): "Avances clave: catalog-service (PostgreSQL), main-process-service (MongoDB), API Gateway y caché en Redis.",
    (2, "TextBox 24", 0): "Demostración en vivo de flujos end-to-end con 29 pruebas unitarias pasando y preservación de privacidad NOM-035.",

    # SLIDE 3
    (3, "TextBox 24", 0): "Bienestar",
    (3, "TextBox 24", 1): "Nexum",
    (3, "TextBox 25", 0): "Requerimientos implementados",
    (3, "TextBox 29", 0): "RF-01: JWT y RBAC. RF-02: CRUD catálogos y campañas en PostgreSQL con baja lógica. RF-03: Evaluaciones, solicitudes y eventos en MongoDB (D-01: anonimato). RF-04: Contratos duales JSON/XML.",
    (3, "TextBox 26", 0): "Integración entre componentes",
    (3, "TextBox 30", 0): "Monolito/Gateway perimetral con enrutamiento REST versionado (/api/v1). Negociación de contenido (Accept/format). Inserción desacoplada de eventos de auditoría y procesos.",
    (3, "TextBox 27", 0): "Servicios desarrollados",
    (3, "TextBox 31", 0): "catalog-service (:3002, PostgreSQL 15, Redis). main-process-service (:3003, MongoDB 7). Monolito Web / Gateway (:3000, JWT, sesiones Redis).",
    (3, "TextBox 28", 0): "Criterios de validación",
    (3, "TextBox 32", 0): "29 pruebas unitarias automatizadas (100% pasando). Contratos validados contra schemas XSD y OpenAPI 3.0. Cumplimiento estricto D-01: cero empleado_id en MongoDB.",

    # SLIDE 4
    (4, "TextBox 61", 0): "Persistencia",
    (4, "TextBox 61", 1): "Políglota",
    (4, "TextBox 57", 0): "Microservicios desacoplados",
    (4, "TextBox 62", 0): "catalog-service (gestión de unidades, instrumentos, reactivos) y main-process-service (encuestas, solicitudes, eventos) operan con ciclo de vida independiente en Docker.",
    (4, "TextBox 58", 0): "Persistencia políglota",
    (4, "TextBox 63", 0): "PostgreSQL 15 gestiona catálogos con integridad referencial y baja lógica. MongoDB 7 procesa respuestas y solicitudes usando seudonimo_id sin JOINs (Regla D-01 NOM-035).",
    (4, "TextBox 59", 0): "Gateway & Contratos duales",
    (4, "TextBox 64", 0): "API Gateway centraliza el enrutamiento REST (/api/v1). Soporte transparente para JSON y XML con schema XSD. Caché distribuida en Redis 7 con invalidación automática.",
    (4, "TextBox 60", 0): "Infraestructura & Trazabilidad",
    (4, "TextBox 65", 0): "Despliegue modular en Docker Compose. Health checks (/health), bitácora de auditoría transaccional en PostgreSQL y registro de eventos en MongoDB con correlacion_id.",

    # SLIDE 5
    (5, "TextBox 31", 0): "Flujo",
    (5, "TextBox 31", 1): "End-to-End",
    (5, "TextBox 32", 0): "1. Entrada y validación",
    (5, "TextBox 35", 0): "Petición POST /api/v1/encuestas/respuestas o catálogos en JSON o XML. El Gateway valida JWT (COLAB/ADMIN), extrae contexto y enruta al microservicio correspondiente.",
    (5, "TextBox 33", 0): "2. Proceso y regla de privacidad",
    (5, "TextBox 36", 0): "main-process-service valida campaña y consentimiento en PostgreSQL. Verifica ausencia de empleado_id para garantizar anonimato estricto (Regla D-01 NOM-035).",
    (5, "TextBox 34", 0): "3. Persistencia y retorno dual",
    (5, "TextBox 37", 0): "Inserción en MongoDB (respuestas_encuesta), registro en eventos_proceso, invalidación en Redis y retorno exitoso (201 Created) en XML o JSON según Accept header.",

    # SLIDE 6 (Core de Ricardo)
    (6, "TextBox 23", 0): "Aportación Integrante 2 · Ricardo Sánchez (#583928)",
    (6, "TextBox 34", 0): "main-process-service (:3003 · MongoDB)",
    (6, "TextBox 36", 0): "Proceso central de evaluaciones y apoyo. Endpoints: POST /api/v1/encuestas/respuestas, GET /agregados/resumen (pipelines $match/$group), POST/PATCH /solicitudes-apoyo (historial con $push), GET /eventos-proceso. Cumple estrictamente la regla D-01: persiste seudonimo_id sin datos de identidad en MongoDB.",
    (6, "TextBox 35", 0): "catalog-service (:3002 · PostgreSQL)",
    (6, "TextBox 37", 0): "Gestión integral de catálogos institucionales. Endpoints: CRUD en /api/v1/catalogos/{unidades, instrumentos, versiones, reactivos, campanias}. Migración SQL 04 con baja lógica (activa=false), constraints de unicidad, triggers, caché en Redis e interoperabilidad dual XML/JSON con schema XSD.",

    # SLIDE 7
    (7, "TextBox 9", 0): "UDEM · Nexum",
    (7, "TextBox 9", 1): "Equipo 03",
    (7, "TextBox 28", 0): "Node.js 20 · Express · PostgreSQL 15 · MongoDB 7 · Redis 7 · Docker Compose · OpenAPI 3.0 · XML / XSD · JWT",
    (7, "TextBox 25", 0): "Despliegue y Contenedores",
    (7, "TextBox 29", 0): "catalog-service (:3002) y main-process-service (:3003) con Dockerfile propio y compose modular (docker-compose.microservicios.yml). Variables de entorno centralizadas en .env.",
    (7, "TextBox 26", 0): "Interoperabilidad y Contratos",
    (7, "TextBox 30", 0): "Contratos duales estandarizados con namespace http://nexum.com.mx/bienestar/v1. Schemas XSD formales para catálogos y procesos. Endpoints retrocompatibles montados en el Gateway.",
    (7, "TextBox 27", 0): "Pruebas y Verificación",
    (7, "TextBox 31", 0): "29 pruebas unitarias automatizadas pasando (100% de éxito). Especificaciones OpenAPI 3.0 validadas. Migraciones SQL probadas y sincronización completa con Google Drive.",

    # SLIDE 8
    (8, "TextBox 22", 0): "Flujo",
    (8, "TextBox 22", 1): "Rúbrica",
    (8, "TextBox 23", 0): "Escenario de prueba (Integrante 2)",
    (8, "TextBox 26", 0): "Login como COLAB → POST /api/v1/encuestas/respuestas con XML → Validación Postgres → Persistencia anonimizada en MongoDB → Emisión de evento en eventos_proceso.",
    (8, "TextBox 27", 0): "1. Iniciar contenedores con Docker Compose. 2. Enviar encuesta vía curl/Postman con Accept: application/xml. 3. Inspeccionar respuesta XML y colección en MongoDB.",
    (8, "TextBox 28", 0): "Respuesta HTTP 201 Created con XML válido según schema XSD. Registro trazable en eventos_proceso y bitacora_auditoria. Cero exposición de datos personales (NOM-035).",

    # SLIDE 9
    (9, "TextBox 21", 0): "Parcial 2",
    (9, "TextBox 25", 0): "catalog-service y main-process-service 100% operativos. CRUD de catálogos con baja lógica en Postgres y motor de encuestas con agregaciones analíticas e historial en MongoDB.",
    (9, "TextBox 23", 0): "Ajustes y optimizaciones",
    (9, "TextBox 26", 0): "Ajustes implementados: serialización dual XML/JSON transparente, invalidación de caché Redis, índices compuestos en Mongo e independización de puertos (:3002 y :3003).",
    (9, "TextBox 24", 0): "Validación e integración",
    (9, "TextBox 27", 0): "29 pruebas unitarias automatizadas pasando al 100%. Contratos OpenAPI 3.0 y schemas XSD validados. Integración transparente al Gateway manteniendo retrocompatibilidad total.",

    # SLIDE 10
    (10, "TextBox 25", 0): "Bienestar",
    (10, "TextBox 25", 1): "Nexum",
    (10, "TextBox 27", 0): "Desacoplamiento efectivo: catalog-service y main-process-service aíslan responsabilidades y ciclos de despliegue.",
    (10, "TextBox 28", 0): "Privacidad garantizada: la regla D-01 separa identidad operativa y personal, asegurando cumplimiento NOM-035.",
    (10, "TextBox 29", 0): "Interoperabilidad robusta: persistencia políglota (PostgreSQL + MongoDB) y contratos duales JSON/XML listos para producción.",
    (10, "TextBox 30", 0): "¿Preguntas? — Demostración técnica y arquitectura abierta a revisión"
}

def main():
    src_pptx = "Plataforma.pptx"
    backup_pptx = "Plataforma_backup.pptx"
    out_pptx = "Plataforma_updated.pptx"

    if not os.path.exists(backup_pptx):
        shutil.copy2(src_pptx, backup_pptx)
        print(f"Copia de seguridad creada en {backup_pptx}")

    applied = set()

    with zipfile.ZipFile(src_pptx, 'r') as zin, zipfile.ZipFile(out_pptx, 'w', compression=zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            import re
            m = re.match(r'^ppt/slides/slide(\d+)\.xml$', item.filename)
            if m:
                slide_num = int(m.group(1))
                root = ET.fromstring(data)

                for sp in root.iter('{http://schemas.openxmlformats.org/presentationml/2006/main}sp'):
                    cNvPr = sp.find('.//{http://schemas.openxmlformats.org/presentationml/2006/main}cNvPr')
                    sp_name = cNvPr.get('name') if cNvPr is not None else 'unknown'
                    txBody = sp.find('{http://schemas.openxmlformats.org/presentationml/2006/main}txBody')
                    if txBody is not None:
                        paragraphs = txBody.findall('{http://schemas.openxmlformats.org/drawingml/2006/main}p')
                        for p_idx, p in enumerate(paragraphs):
                            key = (slide_num, sp_name, p_idx)
                            if key in UPDATES:
                                runs = p.findall('{http://schemas.openxmlformats.org/drawingml/2006/main}r')
                                if runs:
                                    # Set text on first run
                                    t = runs[0].find('{http://schemas.openxmlformats.org/drawingml/2006/main}t')
                                    if t is not None:
                                        t.text = UPDATES[key]
                                    else:
                                        new_t = ET.SubElement(runs[0], '{http://schemas.openxmlformats.org/drawingml/2006/main}t')
                                        new_t.text = UPDATES[key]
                                    
                                    # Remove extra runs in this paragraph if any
                                    for extra_r in runs[1:]:
                                        p.remove(extra_r)
                                    
                                    applied.add(key)

                # Re-serialize slide XML
                new_data = ET.tostring(root, encoding='utf-8', xml_declaration=True)
                zout.writestr(item, new_data)
            else:
                zout.writestr(item, data)

    print(f"Total modificaciones planificadas: {len(UPDATES)}")
    print(f"Total modificaciones aplicadas: {len(applied)}")

    missing = set(UPDATES.keys()) - applied
    if missing:
        print("ADVERTENCIA: No se aplicaron las siguientes claves:")
        for m in missing:
            print("  ", m)
    else:
        print("¡Todas las modificaciones se aplicaron exitosamente!")

    # Reemplazar archivo original con la versión actualizada
    shutil.copy2(out_pptx, src_pptx)
    print(f"Archivo {src_pptx} actualizado con éxito.")

if __name__ == '__main__':
    main()
