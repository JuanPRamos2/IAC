# IAC — Integración de Aplicaciones Computacionales (SC3705)

Portafolio y aplicación del curso. La carpeta que se llamaba
`cloud_models_classifier` quedó repartida así:

| Antes | Ahora |
| --- | --- |
| Proyecto Java `cloud_models_classifier` | `app/` |
| Sitio HTML del curso | `web/` |

`web/` es el sitio general (inicio, ejercicios, simulador). `app/` es la
aplicación Java (GUI + CLI) y el sitio donde encaja un monolito posterior
(por ejemplo un servidor que sirva `web/` y reutilice `classifier`).

## Sitio

```bash
python3 -m http.server 8000 --directory web
```

Abre [http://127.0.0.1:8000](http://127.0.0.1:8000).

- Inicio: `web/index.html`
- Ejercicios: `web/ejercicios.html`
- Ejercicio guiado 1: `web/ejercicios/eg01.html`
- Simulador en el navegador: `web/simulador.html`

Copia tu foto a `web/img/foto.jpg` y las capturas a `web/img/screenshots/`
(nombres en el ejercicio 1).

## Aplicación Java

Hace falta JDK 17 o superior.

```bash
bash app/compile.sh
bash app/run-tests.sh
bash app/run-cli.sh
bash app/run-gui.sh
```

Clases (las mismas del ejercicio guiado 1):

- `ui.CloudClassifierApp` / `ui.ClassifierWindow` — GUI
- `cli.CloudClassifier` — CLI
- `classifier.ClassifierService` — validación y orquestación
- `classifier.RegexClassifier` / `classifier.NlpClassifier`
- `classifier.TextPreprocessor`
- `util.InputValidator`

## Qué no se sube a GitHub

`.jdk/`, `bin/`, `*.class` y secretos. Ver `.gitignore`.
