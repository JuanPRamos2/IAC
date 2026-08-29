# Arquitectura de IAC

El repositorio es un **sitio web monolítico**. La carpeta `web/` reemplaza a
`cloud_models_classifier`: ya no es un script suelto, es la aplicación.

## Capas

```
navegador  →  blueprints (páginas + API)
                    ↓
              services (lógica de negocio)
                    ↓
              models (persistencia, cuando exista)
```

| Ruta | Rol |
| --- | --- |
| `web/factory.py` | Crea la app Flask |
| `web/blueprints/pages.py` | HTML |
| `web/blueprints/api.py` | JSON (`/api/salud`, `/api/clasificar`) |
| `web/services/classifier/` | Clasificador IaaS / PaaS / SaaS / FaaS |
| `web/models/` | Futuras entidades de base de datos |
| `web/extensions.py` | Futuras extensiones (SQLAlchemy, login, etc.) |
| `web/templates/` y `web/static/` | Interfaz |

## Cómo agregar un módulo

1. Servicio en `web/services/<modulo>/`.
2. Rutas en un blueprint nuevo o en los existentes.
3. Plantilla en `web/templates/` si hay UI.
4. Pruebas en `tests/`.

No hace falta un microservicio nuevo para cada feature.

## Configuración

Las variables viven en `.env` (ignorado por git). `.env.example` es la plantilla
pública. El clasificador necesita `OPENROUTER_API_KEY` para las llamadas reales.
