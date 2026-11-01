# idf-calculator — API des prochains trains IDF

API REST simplifiée pour consulter les prochains départs (RER, Transilien, TER) d'une gare
du réseau Île-de-France Mobilités. Elle s'appuie sur l'API temps réel
[PRIM « Prochains passages »](https://prim.iledefrance-mobilites.fr/fr/apis/idfm-ivtr-requete_unitaire)
et renvoie un JSON simplifié à la place du format SIRI brut.

## Démarrage

1. Créez un compte gratuit sur [PRIM](https://prim.iledefrance-mobilites.fr) et générez une clé API.
2. Copiez `.env.example` en `.env` et renseignez `IDF_PRIM_API_KEY`.
3. Lancez :

```bash
uv sync
uv run uvicorn idf_trains.main:app --reload
```

Documentation interactive : http://localhost:8000/docs

## Frontend (Svelte)

Interface web dans `frontend/` (Svelte 5 + Vite + TypeScript) : recherche de gare tolérante aux fautes,
prochains départs rafraîchis toutes les 30 s, filtre par ligne, retards et suppressions, gares récentes,
lien partageable (`#/gare/45102`), thème clair/sombre automatique.

Pages :

- `#/` : recherche d'une gare et prochains départs ;
- `#/trajet?from=…&to=…` : choix d'une gare de départ et d'arrivée, prochains trains directs, sauvegarde ;
- `#/trajets` : trajets sauvegardés avec le prochain train de chacun ;
- `#/trajets/{id}` : détail d'un trajet (renommer, supprimer, trajet retour).

**Développement** (API sur le port 8000, Vite relaie les appels `/stations`) :

```bash
uv run uvicorn idf_trains.main:app --reload   # terminal 1
cd frontend && npm install && npm run dev     # terminal 2 -> http://localhost:5173
```

**Production** : compilez le frontend, FastAPI le sert directement sur `/` :

```bash
cd frontend && npm run build
uv run uvicorn idf_trains.main:app            # -> http://localhost:8000
```

## Endpoints

| Méthode | Route | Description |
|---|---|---|
| GET | `/stations?q=chatelet&line=A` | Recherche de gares (accents facultatifs, filtre par ligne) |
| GET | `/stations/search?name=gare de lyn` | Recherche approximative par nom (fautes tolérées), triée par score |
| GET | `/stations/{id}` | Détail d'une gare et ses lignes |
| GET | `/stations/{id}/departures?line=A&limit=10` | Prochains départs en temps réel |
| GET | `/journeys/next?from=45102&to=470195` | Prochains trains **directs** d'une gare à une autre |
| GET | `/journeys` | Trajets sauvegardés |
| POST | `/journeys` | Sauvegarder un trajet `{"origin_id", "destination_id", "name"?}` |
| GET | `/journeys/{id}` | Détail d'un trajet sauvegardé |
| PATCH | `/journeys/{id}` | Renommer `{"name"}` |
| DELETE | `/journeys/{id}` | Supprimer |
| GET | `/journeys/{id}/next` | Prochains trains d'un trajet sauvegardé |
| GET | `/health` | Healthcheck |

Exemple : `GET /stations/45102/departures?line=A`

```json
{
  "station": {"id": "45102", "name": "Châtelet - Les Halles", "city": "Paris", "lines": [...]},
  "updated_at": "2026-11-01T15:00:00Z",
  "departures": [
    {
      "line": {"id": "C01742", "name": "A", "mode": "RER"},
      "destination": "Cergy le Haut",
      "mission": "QIKI",
      "platform": "A",
      "aimed_time": "2026-11-01T15:03:00Z",
      "expected_time": "2026-11-01T15:05:00Z",
      "in_minutes": 5,
      "delay_minutes": 2,
      "status": "delayed",
      "at_platform": false
    }
  ]
}
```

### Trajets (gare de départ → gare d'arrivée)

`GET /journeys/next?from=45102&to=470195` (Châtelet → Gare de Lyon) :

```json
{
  "origin": {"id": "45102", "name": "Châtelet - Les Halles", "...": "..."},
  "destination": {"id": "470195", "name": "Gare de Lyon", "...": "..."},
  "common_lines": [{"id": "C01742", "name": "A", "mode": "RER"}, {"id": "C01728", "name": "D", "mode": "RER"}],
  "updated_at": "2026-11-01T15:50:00Z",
  "stale": false,
  "trains": [
    {
      "line": {"id": "C01742", "name": "A", "mode": "RER"},
      "destination": "Boissy-Saint-Léger",
      "expected_departure": "2026-11-01T15:56:00Z",
      "expected_arrival": "2026-11-01T15:58:00Z",
      "in_minutes": 6,
      "duration_minutes": 2,
      "delay_minutes": 0,
      "status": "onTime"
    }
  ],
  "message": null
}
```

**Fonctionnement** : l'API récupère les prochains passages aux deux gares (avec le cache) et retient les trains
présents aux deux (même identifiant de course SIRI, ou à défaut même ligne + n° de train) qui passent à la gare
d'arrivée *après* la gare de départ. Le train dessert donc bien la gare d'arrivée, dans le bon sens.

- Seuls les trajets **directs** (sans correspondance) sont gérés. Si les deux gares n'ont aucune ligne en commun,
  la réponse est vide avec un `message`, sans appel à PRIM, et la sauvegarde est refusée (422).
- La gare d'arrivée n'annonce que ses prochains passages (environ 1 à 2 h) : un trajet très long peut n'apparaître
  qu'à l'approche du train.

Les trajets sauvegardés sont stockés dans une base SQLite (`IDF_DB_PATH`, par défaut `data/journeys.db`).
Un même trajet (départ + arrivée) ne peut être sauvegardé qu'une fois (409) ; le sens inverse est un autre trajet.

### Recherche par nom

`GET /stations/search?name=chatlet&limit=3&min_score=0.65` renvoie les gares les plus proches avec un score de 0 à 1
(1 = nom exact) :

```json
[{"score": 0.835, "station": {"id": "45102", "name": "Châtelet - Les Halles", "...": "..."}}]
```

Accents, ponctuation et mots courants (« gare », « de », « la »…) sont ignorés ; « st »/« ste » valent « saint »/« sainte ».

## Cache

Les réponses PRIM sont mises en cache par gare pour ménager le quota et accélérer les réponses :

- **Fraîcheur** : une réponse est resservie sans rappeler PRIM pendant `IDF_CACHE_TTL` secondes (30 par défaut).
  Les champs `in_minutes` sont recalculés à chaque requête.
- **Secours** : si PRIM est en erreur, la dernière donnée connue est renvoyée tant qu'elle a moins de
  `IDF_CACHE_STALE_TTL` secondes (300 par défaut), avec `"stale": true` dans la réponse.
- **Anti-rafale** : des requêtes simultanées sur une même gare ne déclenchent qu'un seul appel PRIM.
- **En-têtes** : `X-Cache: HIT | MISS | STALE`, `Age` (âge de la donnée en secondes) et `Cache-Control`.

Backends :

| Backend | Activation | Usage |
|---|---|---|
| Mémoire (LRU) | par défaut, taille `IDF_CACHE_MAX_ENTRIES` | une seule instance |
| Redis | `uv sync --extra redis` + `IDF_REDIS_URL=redis://localhost:6379/0` | plusieurs instances / workers |

## Référentiel des gares

`data/stations.json` est généré à partir du jeu de données open data
[arrets-lignes](https://data.iledefrance-mobilites.fr/explore/dataset/arrets-lignes/) (export JSON) :

```bash
uv run python scripts/build_stations.py arrets-lignes.json data/stations.json
```

L'identifiant d'une gare est celui de sa zone d'arrêt IDFM (`IDFM:monomodalStopPlace:45102` → `45102`).

## Tests

```bash
uv run pytest
```
