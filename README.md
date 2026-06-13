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
- 🏆 **Simulación del torneo completo**: con los **grupos oficiales del sorteo** (48 equipos en 12 grupos), clasificación (1°, 2° + 8 mejores 3°) y el **cuadro oficial FIFA** de eliminatorias (emparejamientos fijos + asignación de terceros + desempate por enfrentamiento directo) hasta el campeón. Los grupos y el cuadro viven en `data/groups_2026.json` y `data/ko_bracket_2026.json` (editables).
- 📅 **Fixture completo (104 partidos)**: una tarjeta por partido con día/hora/sede/TV, botón **Simular** por partido y **Simular todos**. Datos del calendario editables en `data/fixture_2026.json`.
- 🇪🇸 **Nombres de selecciones en español** (`data/teams_es.json`).
- 🎲 **Monte Carlo configurable**: vos elegís cuántas simulaciones correr. Más simulaciones ⇒ estimaciones más estables.
- 📊 **Datos en vivo**: consulta cuotas y ratings en el momento de simular (con caché corta para respetar los límites de las APIs gratuitas).
- ↻ **Refresco de Elo a requerimiento**: un botón descarga los ratings actuales desde una fuente abierta (gratis, sin clave) — sin polling automático, no gasta tus APIs.
- 🧮 **Modelo híbrido**: ataque/defensa Dixon-Coles ajustado con datos abiertos (con fallback Elo) + el mercado de apuestas como ancla, mezclados con un peso configurable.
- 🎨 **UI minimalista**: una sola pantalla con pestañas Partido / Torneo, responsive.
- 🔌 **Funciona sin claves**: arranca con un dataset Elo semilla y suma las cuotas cuando configurás las APIs.

---

## 🧠 Cómo funciona el modelo

```
Cuotas 1X2 (casas)        ──►  prob. implícitas sin vig  ──┐
                                                           ├─►  λ local / λ visitante  ─►  Monte Carlo (N sims)  ─►  predicción
Ataque/Defensa (Dixon-Coles, datos abiertos)  ─► goles  ──┘    muestreando de la matriz Dixon-Coles
   (fallback Elo si falta histórico)
```

1. **Fuerza de equipos — ataque y defensa independientes.** Cada selección tiene un parámetro de **ataque** (cuánto marca) y otro de **defensa** (cuánto evita que le marquen), ajustados con un modelo **Dixon-Coles** sobre miles de partidos internacionales reales (datos abiertos, dominio público). A diferencia de un Elo único, esto hace que **los goles totales dependan del cruce**: un goleador contra una defensa floja produce muchos goles; dos defensas sólidas, pocos.

   ```
   log λ_local = μ + ventaja_anfitrión + ataque[local] − defensa[visitante]
   log λ_visit = μ +                     ataque[visit]  − defensa[local]
   ```
2. **Sede neutral + anfitriones.** El Mundial se juega en cancha neutral, así que por defecto **no hay ventaja de localía**. La excepción son los anfitriones (🇺🇸/🇲🇽/🇨🇦), que reciben la ventaja calibrada cuando enfrentan a un no-anfitrión.
3. **Mercado como ancla (opcional).** Si hay cuotas, se convierten a probabilidad sin *vig*, se calibran a λ y se mezclan con el modelo de fuerzas (peso `MARKET_BLEND_WEIGHT`).
4. **Monte Carlo consistente.** Se simulan *N* partidos **muestreando de la misma matriz Dixon-Coles** que produce las probabilidades analíticas (antes muestreaba Poisson independientes, lo que sesgaba empates/marcadores bajos). En la eliminatoria se juega **alargue** antes de los **penales** (estos casi una moneda al aire, con leve sesgo por Elo).

> Si una selección no tiene histórico suficiente, ese cruce cae automáticamente al modelo **Elo** y todo sigue funcionando. La calibración es opcional: sin `data/model_params.json` la app arranca con Elo.

### 🔬 Calibrar el modelo con datos abiertos

```bash
python scripts/calibrate.py            # baja resultados reales y ajusta ataque/defensa
python scripts/calibrate.py --since 2014 --half-life 1095 --reg 5
```

Descarga el dataset público [martj42/international_results](https://github.com/martj42/international_results) (CC0, todos los internacionales A), pondera los partidos por **recencia** (vida media configurable) e **importancia** (un Mundial pesa más que un amistoso) y ajusta por máxima verosimilitud `ataque`/`defensa` por selección + `μ`, ventaja de anfitrión y `ρ` (Dixon-Coles). Escribe `data/model_params.json`, que la app carga al arrancar.

### 📈 Validación (backtest out-of-sample)

```bash
python scripts/backtest.py     # entrena hasta 2023, valida 2023, evalúa 2024+
```

`scripts/backtest.py` hace validación temporal sin filtraciones (entrena con datos viejos, evalúa con partidos que el modelo **nunca vio**) y compara el modelo nuevo contra el viejo (Elo de razón-constante) y un baseline. Sobre **2.541 partidos de 2024–2026**, el modelo ataque/defensa gana en todas las métricas:

| modelo | log-loss | Brier | RPS | log-vero. marcador | MAE goles totales |
|---|---|---|---|---|---|
| baseline | 1.054 | 0.636 | 0.227 | −3.204 | 1.455 |
| Elo razón-constante (viejo) | 0.893 | 0.525 | 0.173 | −2.948 | 1.531 |
| **ataque/defensa (nuevo)** | **0.864** | **0.508** | **0.167** | **−2.860** | **1.400** |

El dato clave: el Elo viejo predice el **total de goles peor que el baseline** (1.531 vs 1.455) — es el síntoma del supuesto de goles-totales-constantes. El modelo nuevo lo corrige (1.400) y además acierta mejor el **marcador exacto** (log-verosimilitud). La curva de calibración (predicho vs observado) es casi perfecta, así que no hace falta recalibrar.

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

## 📲 Resumen diario por WhatsApp (Evolution API)

Si configurás Evolution API, la app manda **todos los días** a la hora elegida (default **07:30**, hora argentina) el listado de los partidos del día a una lista de teléfonos:

```
⚽ Partidos de hoy — sábado 13 de junio

16:00 hs   🇶🇦 Catar vs Suiza 🇨🇭
19:00 hs   🇧🇷 Brasil vs Marruecos 🇲🇦
22:00 hs   🇭🇹 Haití vs Escocia 🏴󠁧󠁢󠁳󠁣󠁴󠁿
```

| Variable | Para qué |
|----------|----------|
| `EVOLUTION_API_URL` | URL del servidor de Evolution API. |
| `EVOLUTION_INSTANCE` | Nombre de la instancia. |
| `EVOLUTION_API_KEY` | API key de la instancia. |
| `WHATSAPP_PHONES_FILE` | Ruta al JSON de teléfonos (opcional; default `data/phones.json`). |
| `DAILY_SEND_TIME` | Hora del envío `HH:MM` (default `07:30`). |
| `DAILY_TIMEZONE` | Zona horaria (default `America/Argentina/Buenos_Aires`). |

**Teléfonos** — copiá `data/phones.example.json` a `data/phones.json` (este último está en `.gitignore`) con el formato `{ "nombre": "telefono" }`, en formato internacional sin signos:

```json
{ "Pablo": "5491112345678", "Juan": "5492213334444" }
```

- El envío es **idempotente por día** (no manda duplicados si el proceso se reinicia).
- Probar/forzar a mano: `python scripts/send_daily.py --dry-run` (muestra el mensaje sin enviar) o sin `--dry-run` para enviar. También vía API: `POST /api/send-daily?dry_run=true`.
- Si preferís no depender del proceso web, agendá `scripts/send_daily.py` con cron / Programador de tareas.

> Sin las variables `EVOLUTION_*` la función queda desactivada y el resto de la app funciona igual.

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
    schedule.py        arma el fixture de 104 partidos para la UI
    daily.py           resumen diario de partidos + scheduler 07:30
    whatsapp.py        cliente de Evolution API (envío de mensajes)
    flags.py           código FIFA → bandera emoji (WhatsApp)
  model/
    poisson.py         matriz Dixon-Coles, muestreo, calibración al mercado
    fitting.py         ajuste por MLE del modelo ataque/defensa (gradiente analítico)
    strengths.py       λ por ataque/defensa (o Elo de fallback) + anfitriones
    params.py          carga los parámetros calibrados (model_params.json)
    montecarlo.py      motor de N simulaciones (muestrea de la matriz DC)
    tournament.py      simulación del Mundial completo (grupos + eliminatoria)
    blend.py           mezcla mercado ↔ modelo de fuerzas (en espacio log)
data/elo_ratings.csv   ratings semilla / fallback
data/model_params.json ataque/defensa + μ/ventaja/ρ calibrados (lo crea calibrate.py)
data/groups_2026.json  grupos oficiales del sorteo (editable)
data/phones.json       teléfonos del resumen WhatsApp (en .gitignore; ver .example)
scripts/calibrate.py   ajusta el modelo con datos abiertos de partidos reales
scripts/backtest.py    validación out-of-sample (nuevo vs viejo vs baseline)
scripts/send_daily.py  envía/previsualiza el resumen diario por WhatsApp
static/                index.html + app.js (UI)
tests/                 sanidad del modelo + chequeo de gradiente
Dockerfile             imagen para EasyPanel / Docker
render.yaml            blueprint para Render
```

---

## 🔌 Endpoints

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/api/matches` | Equipos disponibles, nombres en español y estado de fuentes. |
| `GET` | `/api/fixture` | Los 104 partidos con día/hora/sede/TV. |
| `POST` | `/api/simulate` | Predicción de un partido (`home_team`, `away_team`, `n_simulations`). |
| `POST` | `/api/simulate-tournament` | Simula el Mundial completo (`n_simulations`). |
| `POST` | `/api/refresh-ratings` | Actualiza los Elo en vivo (a requerimiento). |
| `POST` | `/api/send-daily` | Envía el resumen de hoy por WhatsApp (`?dry_run=true` solo previsualiza). |

### Cargar el calendario (`data/fixture_2026.json`)

Si este archivo existe, la app lo usa; si no, genera los 104 partidos automáticamente
(con día/hora/TV vacíos). Formato:

```json
{
  "matches": [
    {
      "n": 1,
      "stage": "group",
      "group": "A",
      "home": "Mexico",
      "away": "South Korea",
      "date": "2026-06-11",
      "time": "21:00",
      "venue": "Estadio Azteca, Ciudad de México",
      "tv": ["TV Pública", "Telefe", "DSports"]
    }
  ]
}
```

- `home`/`away` aceptan **nombre en inglés, en español o el código** (ej. `MEX`).
- Para partidos de eliminatoria sin rival definido, usá `home_label`/`away_label`
  (ej. `"Ganador 73"`) y dejá `home`/`away` en `null`.
- `stage`: `group`, `r32`, `r16`, `qf`, `sf`, `third`, `final`.
- `time` en hora de Argentina; `tv` es una lista de señales.

## 🗺️ Roadmap

- [x] Refresco de Elo **a requerimiento** (fuente abierta, sin gastar APIs).
- [x] Simulación del **torneo completo** (grupos → llaves → campeón probable).
- [x] **Grupos oficiales del sorteo** cargados desde `data/groups_2026.json` (editable).
- [ ] Mapeo exacto del cuadro de eliminatoria según las posiciones FIFA.
- [ ] Historial de predicciones y comparación contra resultados reales.

---

## ⚠️ Aviso

Predicción estadística con fines orientativos y educativos. **No constituye consejo de apuestas.**
