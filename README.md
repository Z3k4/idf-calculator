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

## Docker

Une seule image contient l'API et le frontend compilé (construction en plusieurs étapes : Node pour le build Svelte,
uv pour les dépendances Python, image finale `python:3.12-slim` d'environ 170 Mo, exécutée par un utilisateur sans
privilèges).

```bash
cp .env.example .env            # renseignez IDF_PRIM_API_KEY
docker compose up -d --build    # http://localhost:8000
docker compose logs -f
```

- **Données** : la base SQLite (trajets et itinéraires sauvegardés, accueil, cache des adresses, consommation) est
  stockée dans le volume `idf-data` (`/data` dans le conteneur). Elle est conservée entre redémarrages et mises à jour.
- **Port** : `IDF_PORT=8080 docker compose up -d` pour publier sur un autre port.
- **Redis** (facultatif, cache partagé) : `docker compose --profile redis up -d` et ajoutez
  `IDF_REDIS_URL=redis://redis:6379/0` dans `.env`.
- **Santé** : healthcheck intégré sur `/health`.
- **Sans compose** :

```bash
docker build -t idf-trains .
docker run -d -p 8000:8000 --env-file .env -v idf-data:/data --name idf-trains idf-trains
```

- **Mise à jour** : `git pull && docker compose up -d --build`. Les données du volume sont conservées et le schéma de la
  base est migré automatiquement.
- Derrière un reverse proxy (HTTPS), les en-têtes `X-Forwarded-*` sont pris en compte.

Testé avec Podman 5 (`podman build`, `podman compose`), compatible Docker.

## Frontend (Svelte)

Interface web dans `frontend/` (Svelte 5 + Vite + TypeScript) : recherche de gare tolérante aux fautes,
prochains départs rafraîchis toutes les 30 s, filtre par ligne, retards et suppressions, gares récentes,
lien partageable (`#/gare/45102`), thème clair/sombre automatique.

Pages :

- `#/` : **accueil personnalisable par groupes** (ex. « Semaine », « Week-end ») : onglets pour changer à tout moment le groupe affiché (mémorisé dans le navigateur), « + Groupe » pour en créer, « Personnaliser » pour renommer, cocher, ordonner ou supprimer le groupe, avec les prochains trains directs en direct et le meilleur itinéraire calculé à l'ouverture ;
- `#/departs` : recherche d'une gare et prochains départs ;
- `#/itineraire` : itinéraire entre deux adresses (autocomplétion, adresses récentes, « Ma position », partir/arriver à, sauvegarde) ;
- `#/itineraires/{id}` : itinéraire sauvegardé, calculé avec son horaire enregistré (si on change l'horaire : « Remplacer l'horaire » ou « Ajouter avec cet horaire » pour garder les deux, « Modifier » pour changer lieux/nom/horaire, renommer, supprimer, itinéraire retour) ;
- `#/trajet?from=…&to=…` : choix d'une gare de départ et d'arrivée, prochains trains directs, sauvegarde ;
- `#/conso` : consommation des API IDFM (quotas, historique, cache, derniers appels) ;
- `#/trajets` : itinéraires et trajets directs sauvegardés (avec le prochain train pour les trajets directs) ;
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
| GET | `/places?q=12 rue de rivoli` | Recherche d'adresse, arrêt, lieu ou commune (calculateur IDFM) |
| GET | `/itineraries?from=…&to=…` | Itinéraire entre deux lieux (tous modes IDFM) |
| GET | `/itineraries/saved` | Itinéraires sauvegardés |
| POST | `/itineraries/saved` | Sauvegarder `{"origin": <lieu>, "destination": <lieu>, "name"?, "schedule"?}` |
| GET / PATCH / DELETE | `/itineraries/saved/{id}` | Détail / modifier (partiel : `name`, `origin`, `destination`, `schedule`) / supprimer |
| GET | `/itineraries/saved/{id}/next` | Calculer un itinéraire sauvegardé (son horaire enregistré par défaut) |
| GET | `/usage?days=30` | Consommation des API IDFM : appels, quotas, cache, erreurs |
| GET | `/home` | Groupes de la page d'accueil, chacun avec ses trajets et itinéraires (dans l'ordre) |
| POST | `/home/groups` | Créer un groupe `{"name", "items"?: [{"kind": "journey" \| "itinerary", "id"}]}` |
| PATCH / DELETE | `/home/groups/{id}` | Renommer et/ou choisir les éléments (partiel : `name`, `items`) / supprimer (409 pour le dernier groupe) |
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

### Itinéraires entre deux adresses

S'appuie sur le **calculateur d'itinéraires Île-de-France Mobilités** (API Navitia exposée par PRIM,
`https://prim.iledefrance-mobilites.fr/marketplace/v2/navitia`, même clé API). Dans le catalogue PRIM, abonnez-vous
à l'API « Calculateur Île-de-France Mobilités – Accès générique ».

1. `GET /places?q=12 rue de rivoli` renvoie des lieux avec un `id` (adresse : coordonnées `lon;lat`,
   arrêt : `stop_area:IDFM:…`, point d'intérêt, commune).
2. `GET /itineraries?from=<id>&to=<id>` calcule les itinéraires (métro, RER, Transilien, tram, bus, marche) :

| Paramètre | Description |
|---|---|
| `from`, `to` | Identifiant renvoyé par `/places`, ou coordonnées `lon;lat` |
| `date` | Jour `AAAA-MM-JJ`, facultatif. **Sans date : aujourd'hui, ou demain si l'heure indiquée est déjà passée** |
| `time` | Heure `HH:MM`, facultative. **Sans heure : l'heure actuelle** |
| `datetime` | Alternative à `date`/`time` : date et heure ISO 8601 complètes (heure de Paris si sans fuseau) |
| `represents` | `departure` (partir à, défaut) ou `arrival` (arriver avant) |

Sans `date`, `time` ni `datetime`, le calcul part de maintenant. Exemples : à 18h, `time=20:15` signifie aujourd'hui à 20h15
et `time=08:15` signifie **demain** à 8h15 (heure déjà passée, comparée à la minute près) ;
`date=2026-11-05` signifie le 5 novembre à l'heure actuelle. La réponse indique l'horaire effectivement utilisé
(`requested_at`, heure de Paris) et `represents`. Les mêmes paramètres s'appliquent à `/itineraries/saved/{id}/next`.
| `count` | Nombre d'itinéraires (1 à 6, défaut 3) |

Chaque itinéraire donne les horaires, la durée, le nombre de correspondances, la marche, le CO₂ et la liste des
étapes : marche, attente, correspondance et trajets en transport (ligne avec sa couleur officielle, direction,
arrêts desservis, retard temps réel, tracé GeoJSON).

**Itinéraires sauvegardés** : `POST /itineraries/saved` prend les lieux tels que renvoyés par `/places`, et un horaire
par défaut facultatif : `"schedule": {"mode": "now" | "departure" | "arrival", "date": "AAAA-MM-JJ" | null, "time": "HH:MM" | null}`
(mêmes règles que `/itineraries` : sans date, aujourd'hui, ou demain si l'heure est passée). `PATCH` ne modifie que
les champs envoyés. Un même couple départ/arrivée peut être sauvegardé **plusieurs fois avec des horaires
différents** (ex. aller à 8h, retour à 18h) ; un 409 n'est renvoyé que si **un autre** itinéraire a déjà les mêmes
lieux et le même horaire (mode, date, heure). `/itineraries/saved/{id}/next` applique l'horaire
enregistré, sauf si la requête précise `date`, `time` ou `datetime`. Les bases existantes sont migrées automatiquement. Ils sont
stockés en entier (nom, type, coordonnées) dans la base SQLite. « Ma position » (type `position`) est refusée (422), car elle change à chaque utilisation.

**Quota et cache des adresses** : les jetons PRIM récents sont limités à **1 000 requêtes/jour** sur cette API.

- Recherches d'adresses : cache en mémoire 24 h (`IDF_PLACES_CACHE_TTL`), puis **cache persistant SQLite de 30 jours**
  (`IDF_PLACES_DB_TTL`, table `place_searches`), conservé après un redémarrage. Les entrées expirées sont purgées au
  démarrage. Les recherches ne diffèrent que par la casse ou les espaces (« 12  Rue de RIVOLI ») partagent la même entrée.
- Itinéraires : cache de 60 s (`IDF_ITINERARIES_CACHE_TTL`).
- Frontend : les adresses déjà choisies sont mémorisées dans le navigateur et proposées dès qu'on clique dans le champ,
  sans appel à l'API. La recherche attend une pause dans la frappe, et les itinéraires ne se rafraîchissent pas
  automatiquement.

### Recherche par nom

`GET /stations/search?name=chatlet&limit=3&min_score=0.65` renvoie les gares les plus proches avec un score de 0 à 1
(1 = nom exact) :

```json
[{"score": 0.835, "station": {"id": "45102", "name": "Châtelet - Les Halles", "...": "..."}}]
```

Accents, ponctuation et mots courants (« gare », « de », « la »…) sont ignorés ; « st »/« ste » valent « saint »/« sainte ».

## Suivi de la consommation des API IDFM

Chaque appel envoyé à Île-de-France Mobilités est enregistré dans la base SQLite (table `api_calls` : API, service,
code HTTP, durée), ainsi que le nombre de requêtes servies par le cache sans appel (table `cache_hits`).
Les jours sont comptés à l'heure de Paris, comme la remise à zéro des quotas. L'historique est conservé 90 jours
(`IDF_USAGE_RETENTION_DAYS`).

`GET /usage?days=30` renvoie, pour aujourd'hui et par API, les appels, les erreurs, les requêtes évitées par le cache
et le quota restant. S'y ajoutent l'historique par jour, la répartition par heure, le détail par service et les
derniers appels. La page **Conso** du frontend (`#/conso`) l'affiche avec des graphiques, rafraîchis toutes les 30 s.

| Variable | Défaut | Description |
|---|---|---|
| `IDF_QUOTA_NAVITIA` | `1000` | Quota journalier du calculateur d'itinéraires (jetons PRIM récents) |
| `IDF_QUOTA_REALTIME` | *(aucun)* | Quota journalier de l'API temps réel : à renseigner selon votre abonnement PRIM |

Les appels sont comptés **par ce serveur** : si la même clé API est utilisée ailleurs, ces appels-là n'apparaissent pas.

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
