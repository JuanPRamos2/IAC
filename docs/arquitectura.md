# Arquitectura

El repositorio es el curso SC3705, no un clasificador con nombre de producto.

```
IAC
├── web/     sitio del curso (HTML/CSS/JS)
└── app/     aplicación Java (antes cloud_models_classifier)
```

## Sitio (`web/`)

Páginas estáticas con chrome compartido (`js/app.js` inyecta encabezado y pie).
El simulador (`simulador.html`) clasifica en el navegador con las mismas reglas
que la app Java, para poder entregarlo en un servidor tipo ubiquitous sin
compilar.

Para convertir esto en un **monolito**: un proceso (Java o el que se elija)
puede servir `web/` como estáticos y exponer un endpoint que llame a
`ClassifierService`. No hace falta otro repositorio.

## App (`app/`)

```
Usuario
  ├─ GUI  (ClassifierWindow / CloudClassifierApp)
  └─ CLI  (CloudClassifier)
        ▼
 ClassifierService
        ├─ RegexClassifier
        └─ NlpClassifier
```

La GUI no contiene las reglas: captura nombre, apellido y texto, llama al
servicio y muestra el modelo y las puntuaciones.
