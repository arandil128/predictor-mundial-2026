<h1 align="center">⚽ Predictor Mundial 2026</h1>

<p align="center">
  <em>App web que predice el resultado de cada partido del Mundial combinando
  ranking Elo/FIFA, cuotas de casas de apuestas en vivo y simulación Monte Carlo.</em>
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white">
  <img alt="Docker" src="https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white">
  <img alt="Tests" src="https://img.shields.io/badge/tests-6%20passing-success">
</p>

---

## ✨ Características

- 🎯 **Predicción por partido**: probabilidades 1X2, marcador esperado, marcadores más probables, Over 2.5 y Ambos Marcan.
- 🎲 **Monte Carlo configurable**: vos elegís cuántas simulaciones correr (1.000 – 200.000). Más simulaciones ⇒ estimaciones más estables.
- 📊 **Datos en vivo**: consulta cuotas y ratings en el momento de simular (con caché corta para respetar los límites de las APIs gratuitas).
- 🧮 **Modelo híbrido**: el mercado de apuestas como ancla + modelo Elo/FIFA, mezclados con un peso configurable.
- 🎨 **UI minimalista**: una sola pantalla, responsive, sin pasos de más.
- 🔌 **Funciona sin claves**: arranca con un dataset Elo semilla y suma las cuotas cuando configurás las APIs.

---

## 🧠 Cómo funciona el modelo

```
Cuotas 1X2 (casas)  ──►  prob. implícitas sin vig  ──┐
                                                      ├──►  λ local / λ visitante  ──►  Monte Carlo (N sims)  ──►  predicción
Elo + ranking FIFA  ──►  goles esperados (localía)  ──┘                                  Poisson + Dixon-Coles
```

1. **Mercado como ancla** — las cuotas decimales se convierten a probabilidad (`1/cuota`) y se les quita el margen de la casa (*vig*).
2. **Fuerza de equipos** — la diferencia de Elo (más la ventaja de localía) define los goles esperados de cada selección.
3. **Calibración + mezcla** — se calibran los goles esperados para reproducir el mercado y se mezclan con el modelo Elo (peso `MARKET_BLEND_WEIGHT`).
4. **Monte Carlo** — se simulan *N* partidos muestreando goles de sendas distribuciones Poisson; el cálculo analítico aplica la corrección **Dixon-Coles** para marcadores bajos.

> Si todavía no hay cuotas para un cruce (lo habitual hasta cerca del torneo), el modelo trabaja solo con Elo/FIFA y lo avisa en la interfaz.

---

## 🚀 Puesta en marcha (local)

```bash
# 1. Dependencias
python -m venv .venv
.venv\Scripts\activate            # Windows  (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt

# 2. Configuración (opcional: claves de API)
copy .env.example .env            # Windows  (Linux/Mac: cp .env.example .env)

# 3. Levantar
uvicorn app.main:app --reload
```

Abrí **http://127.0.0.1:8000** 🎉

### 🐳 Con Docker

```bash
docker build -t predictor-mundial .
docker run -p 8000:8000 --env-file .env predictor-mundial
```

---

## 🔑 Claves de API (gratuitas, opcionales)

| Variable | Para qué | Registro | Límite free |
|----------|----------|----------|-------------|
| `ODDS_API_KEY` | Cuotas 1X2 en vivo | [the-odds-api.com](https://the-odds-api.com/) | 500 req/mes |
| `FOOTBALL_DATA_API_KEY` | Fixtures/partidos del Mundial | [football-data.org](https://www.football-data.org/) | con registro |
| `API_FOOTBALL_KEY` | Refuerzo de fixtures/stats | [api-football.com](https://www.api-football.com/) | 100 req/día |

Sin claves la app funciona con el dataset Elo semilla (`data/elo_ratings.csv`).

### Parámetros del modelo

| Variable | Default | Descripción |
|----------|---------|-------------|
| `MARKET_BLEND_WEIGHT` | `0.65` | Peso del mercado en la mezcla mercado↔modelo (0–1). |
| `CACHE_TTL_SECONDS` | `300` | Segundos de caché para respuestas de APIs externas. |

---

## ☁️ Despliegue en EasyPanel (Docker)

1. En EasyPanel: **Create → App → Source: GitHub** y elegí este repositorio.
2. **Build**: tipo **Dockerfile** (lo detecta automáticamente; usa el `Dockerfile` del repo).
3. **Environment**: cargá las variables de entorno (`ODDS_API_KEY`, `FOOTBALL_DATA_API_KEY`, etc.).
4. **Port**: `8000` (el contenedor escucha en `$PORT`, default 8000).
5. Deploy. EasyPanel construye la imagen y publica la app con su dominio/SSL.

> También incluye `render.yaml` por si preferís desplegar en Render con un clic.

---

## 🧪 Tests

```bash
pytest -q
```

Cubren la conversión de cuotas (sin vig), la normalización de la matriz de marcadores,
la convergencia del Monte Carlo al resultado analítico y la calibración al mercado.

---

## 📁 Estructura

```
app/
  main.py              API FastAPI + sirve el frontend
  config.py            settings desde .env
  services/
    odds.py            The Odds API → prob. implícitas sin vig
    fixtures.py        football-data.org → partidos/equipos
    ratings.py         carga Elo/FIFA (CSV semilla)
    cache.py           caché en memoria con TTL
  model/
    poisson.py         λ desde Elo, matriz Dixon-Coles, calibración al mercado
    montecarlo.py      motor de N simulaciones
    blend.py           mezcla mercado ↔ modelo
data/elo_ratings.csv   ratings semilla / fallback
static/                index.html + app.js (UI)
tests/                 sanidad del modelo
Dockerfile             imagen para EasyPanel / Docker
render.yaml            blueprint para Render
```

---

## 🗺️ Roadmap

- [ ] Dataset Elo **auto-actualizable** (refresco periódico desde fuente en vivo).
- [ ] Simulación del **torneo completo** (grupos → llaves → campeón probable).
- [ ] Historial de predicciones y comparación contra resultados reales.

---

## ⚠️ Aviso

Predicción estadística con fines orientativos y educativos. **No constituye consejo de apuestas.**
