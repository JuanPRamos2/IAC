# IAC

Sitio web monolítico. El clasificador de servicios en la nube (IaaS, PaaS, SaaS, FaaS)
es el primer módulo, no el nombre del producto.

La carpeta que antes se llamaba `cloud_models_classifier` ahora es `web/`.

## Requisitos

- Python 3.10 o superior
- Una clave de [OpenRouter](https://openrouter.ai/) si quieres clasificar textos de verdad

## Arranque

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env
```

Edita `.env` y pon `OPENROUTER_API_KEY` y un `FLASK_SECRET_KEY` propio.

```bash
python run.py
```

Abre [http://127.0.0.1:5000](http://127.0.0.1:5000).

Producción:

```bash
gunicorn web.wsgi:app
```

Consola (sin servidor web):

```bash
python -m web.cli --cli
python -m web.cli -t "AWS Lambda ejecuta funciones sin servidor"
```

## Estructura

```
.
├── web/                      # aplicación web (monolito)
│   ├── blueprints/           # rutas HTML y API
│   ├── services/classifier/  # lógica del clasificador
│   ├── models/               # sitio para el ORM / persistencia
│   ├── templates/            # páginas
│   └── static/               # CSS y JS
├── tests/                    # pruebas sin API externa
├── docs/                     # arquitectura y evidencias
├── .env.example              # variables, sin secretos
└── run.py                    # desarrollo
```

Detalle en [docs/arquitectura.md](docs/arquitectura.md).

## Pruebas

```bash
pytest
```

Las pruebas de CI no llaman a OpenRouter. El clasificador en vivo se prueba a
mano en `/clasificador` o con el CLI.

## Seguridad

No subas `.env` ni claves. Si una clave llegó a git, rotarla en el proveedor.
