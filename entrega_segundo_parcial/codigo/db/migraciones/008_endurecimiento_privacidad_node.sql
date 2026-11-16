-- ============================================================================
-- Migracion 008: Endurecimiento de Privacidad y Aislamiento de Apoyo (Node.js)
-- ============================================================================
-- 1. Revoca insercion directa en autoreporte para garantizar que todas las
--    respuestas pasen por autoreporte.fn_registrar_autoreporte (SECURITY DEFINER).
REVOKE INSERT ON autoreporte.respuesta, autoreporte.respuesta_detalle FROM bienestar_app;

-- 2. Confidencialidad estricta de Solicitudes de Apoyo:
--    El perfil ADMINISTRADOR de TI no debe tener acceso a atender solicitudes
--    de apoyo emocional ni leer expedientes de colaboradores.
--    El permiso APOYO_ATENDER queda reservado exclusivamente para ESPECIALISTA.
DELETE FROM usuarios.perfil_permiso
 WHERE perfil_codigo = 'ADMINISTRADOR'
   AND permiso_codigo = 'APOYO_ATENDER';
