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

## Endpoints

| Méthode | Route | Description |
|---|---|---|
| GET | `/stations?q=chatelet&line=A` | Recherche de gares (accents facultatifs, filtre par ligne) |
| GET | `/stations/search?name=gare de lyn` | Recherche approximative par nom (fautes tolérées), triée par score |
| GET | `/stations/{id}` | Détail d'une gare et ses lignes |
| GET | `/stations/{id}/departures?line=A&limit=10` | Prochains départs en temps réel |
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
