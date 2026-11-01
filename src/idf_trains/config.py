from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="IDF_", extra="ignore")

    # Clé API PRIM : https://prim.iledefrance-mobilites.fr (compte gratuit)
    prim_api_key: str = ""
    prim_url: str = "https://prim.iledefrance-mobilites.fr/marketplace/stop-monitoring"
    prim_timeout: float = 10.0
    # Cache des réponses PRIM par gare (secondes) :
    # - cache_ttl : durée pendant laquelle la réponse est servie sans rappeler PRIM
    # - cache_stale_ttl : durée max pendant laquelle elle sert de secours si PRIM est en erreur
    cache_ttl: float = 30.0
    cache_stale_ttl: float = 300.0
    cache_max_entries: int = 1000
    # Si renseigné (ex. redis://localhost:6379/0), cache partagé Redis au lieu de la mémoire
    redis_url: str = ""
    stations_file: Path = ROOT / "data" / "stations.json"
    # Base SQLite des trajets sauvegardés
    db_path: Path = ROOT / "data" / "journeys.db"
    # Build du frontend Svelte servi sur « / » (ignoré si absent)
    frontend_dir: Path = ROOT / "frontend" / "dist"


settings = Settings()
