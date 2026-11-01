"""Génère data/stations.json à partir du référentiel IDFM « arrets-lignes ».

Source : https://data.iledefrance-mobilites.fr/explore/dataset/arrets-lignes/ (export JSON)

Usage :
    uv run python scripts/build_stations.py [arrets-lignes.json] [data/stations.json]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Modes ferroviaires conservés -> libellé exposé par l'API
RAIL_MODES = {
    "RapidTransit": "RER",
    "LocalTrain": "Transilien",
    "regionalRail": "TER",
}


def build(src: Path) -> dict:
    rows = json.loads(src.read_text(encoding="utf-8"))

    lines: dict[str, dict] = {}
    stations: dict[str, dict] = {}

    for row in rows:
        mode = RAIL_MODES.get(row.get("mode"))
        if mode is None:
            continue

        line_id = row["id"].removeprefix("IDFM:")
        lines[line_id] = {
            "name": row["shortname"],
            "long_name": row["route_long_name"],
            "mode": mode,
            "operator": row["operatorname"],
        }

        # IDFM:monomodalStopPlace:470195 -> 470195
        station_id = row["stop_id"].rsplit(":", 1)[-1]
        station = stations.setdefault(
            station_id,
            {
                "id": station_id,
                "name": row["stop_name"],
                "city": row["nom_commune"],
                "lat": row["pointgeo"]["lat"],
                "lon": row["pointgeo"]["lon"],
                "lines": [],
            },
        )
        if line_id not in station["lines"]:
            station["lines"].append(line_id)

    for station in stations.values():
        station["lines"].sort(key=lambda lid: (lines[lid]["mode"], lines[lid]["name"]))

    return {
        "lines": dict(sorted(lines.items())),
        "stations": sorted(stations.values(), key=lambda s: s["name"]),
    }


def main() -> None:
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "arrets-lignes.json")
    dst = Path(sys.argv[2] if len(sys.argv) > 2 else "data/stations.json")
    data = build(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(data['stations'])} gares, {len(data['lines'])} lignes -> {dst}")


if __name__ == "__main__":
    main()
