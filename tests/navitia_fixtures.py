"""Réponses Navitia fictives mais au format réel (doc.navitia.io), pour les tests."""

from datetime import datetime, timedelta

FMT = "%Y%m%dT%H%M%S"


def _t(base: datetime, minutes: float) -> str:
    return (base + timedelta(minutes=minutes)).strftime(FMT)


def _place(name, pid, kind="stop_point"):
    return {"id": pid, "name": name, "embedded_type": kind}


def _walk(base, start, end, frm, to, meters, kind="street_network"):
    return {
        "type": kind,
        "mode": "walking",
        "duration": int((end - start) * 60),
        "departure_date_time": _t(base, start),
        "arrival_date_time": _t(base, end),
        "from": frm,
        "to": to,
        "geojson": {"type": "LineString", "coordinates": [[2.35, 48.86], [2.347, 48.861]], "properties": [{"length": meters}]},
    }


def _pt(base, start, end, frm, to, code, mode, color, direction, stops, delay=0, headsign=""):
    return {
        "type": "public_transport",
        "duration": int((end - start) * 60),
        "departure_date_time": _t(base, start + delay),
        "arrival_date_time": _t(base, end + delay),
        "base_departure_date_time": _t(base, start),
        "base_arrival_date_time": _t(base, end),
        "from": frm,
        "to": to,
        "display_informations": {
            "code": code,
            "commercial_mode": mode,
            "physical_mode": mode,
            "network": mode,
            "color": color,
            "text_color": "FFFFFF",
            "direction": direction,
            "headsign": headsign,
            "name": f"{mode} {code}",
        },
        "stop_date_times": [{"stop_point": {"name": s}} for s in stops],
        "geojson": {"type": "LineString", "coordinates": [[2.347, 48.861], [2.238, 48.892]], "properties": []},
    }


def journeys(base: datetime) -> dict:
    start = {"id": "2.3522;48.8566", "name": "12 Rue de Rivoli (Paris)", "embedded_type": "address"}
    end = {"id": "2.2400;48.8920", "name": "1 Parvis de la Défense (Puteaux)", "embedded_type": "address"}
    chatelet = _place("Châtelet les Halles", "stop_point:IDFM:1")
    defense = _place("La Défense", "stop_point:IDFM:2")
    hdv = _place("Hôtel de Ville", "stop_point:IDFM:3")
    defense_m = _place("La Défense (Grande Arche)", "stop_point:IDFM:4")
    pont = _place("Pont de Neuilly", "stop_point:IDFM:5")
    pont_t = _place("Pont de Neuilly - Tram", "stop_point:IDFM:6")

    return {
        "journeys": [
            {
                "type": "best",
                "tags": ["walking", "ecologic"],
                "status": "SIGNIFICANT_DELAYS",
                "duration": 26 * 60,
                "nb_transfers": 0,
                "departure_date_time": _t(base, 2),
                "arrival_date_time": _t(base, 28),
                "durations": {"walking": 11 * 60, "total": 26 * 60},
                "distances": {"walking": 850},
                "co2_emission": {"value": 61.2, "unit": "gEC"},
                "sections": [
                    {"type": "crow_fly", "mode": "walking", "duration": 0, "from": start, "to": start},
                    _walk(base, 2, 7, start, chatelet, 400),
                    {"type": "waiting", "duration": 120, "departure_date_time": _t(base, 7), "arrival_date_time": _t(base, 9)},
                    _pt(base, 9, 21, chatelet, defense, "A", "RER", "E3051C", "Saint-Germain-en-Laye",
                        ["Châtelet les Halles", "Auber", "Charles de Gaulle - Étoile", "La Défense"], delay=2, headsign="UPAC"),
                    _walk(base, 23, 28, defense, end, 450),
                ],
            },
            {
                "type": "comfort",
                "tags": ["walking", "ecologic"],
                "duration": 31 * 60,
                "nb_transfers": 0,
                "departure_date_time": _t(base, 4),
                "arrival_date_time": _t(base, 35),
                "durations": {"walking": 8 * 60, "total": 31 * 60},
                "distances": {"walking": 600},
                "co2_emission": {"value": 48.0, "unit": "gEC"},
                "sections": [
                    _walk(base, 4, 7, start, hdv, 220),
                    _pt(base, 7, 30, hdv, defense_m, "1", "Métro", "FFCD00", "La Défense (Grande Arche)",
                        ["Hôtel de Ville", "Châtelet", "Concorde", "Charles de Gaulle - Étoile", "La Défense (Grande Arche)"]),
                    _walk(base, 30, 35, defense_m, end, 380),
                ],
            },
            {
                "type": "rapid",
                "tags": ["walking"],
                "duration": 38 * 60,
                "nb_transfers": 1,
                "departure_date_time": _t(base, 6),
                "arrival_date_time": _t(base, 44),
                "durations": {"walking": 9 * 60, "total": 38 * 60},
                "distances": {"walking": 700},
                "sections": [
                    _walk(base, 6, 10, start, hdv, 300),
                    _pt(base, 10, 27, hdv, pont, "1", "Métro", "FFCD00", "La Défense (Grande Arche)",
                        ["Hôtel de Ville", "Concorde", "Pont de Neuilly"]),
                    _walk(base, 27, 30, pont, pont_t, 150, kind="transfer"),
                    {"type": "waiting", "duration": 240, "departure_date_time": _t(base, 30), "arrival_date_time": _t(base, 34)},
                    _pt(base, 34, 42, pont_t, defense, "T2", "Tramway", "CF009E", "Pont de Bezons",
                        ["Pont de Neuilly - Tram", "La Défense"]),
                    _walk(base, 42, 44, defense, end, 250),
                ],
            },
        ]
    }


PLACES = {
    "places": [
        {
            "id": "2.3522;48.8566",
            "name": "12 Rue de Rivoli (Paris)",
            "embedded_type": "address",
            "quality": 90,
            "address": {
                "label": "12 Rue de Rivoli (Paris)",
                "coord": {"lon": "2.3522", "lat": "48.8566"},
                "administrative_regions": [{"name": "Paris", "level": 8}, {"name": "Île-de-France", "level": 4}],
            },
        },
        {
            "id": "stop_area:IDFM:71517",
            "name": "Gare de Lyon (Paris)",
            "embedded_type": "stop_area",
            "stop_area": {
                "label": "Gare de Lyon (Paris)",
                "coord": {"lon": "2.3733", "lat": "48.8443"},
                "administrative_regions": [{"name": "Paris", "level": 8}],
            },
        },
        {
            "id": "poi:osm:node:1",
            "name": "Tour Eiffel (Paris)",
            "embedded_type": "poi",
            "poi": {"label": "Tour Eiffel (Paris)", "coord": {"lon": "2.2945", "lat": "48.8584"}},
        },
        {"id": "weird", "name": "Ignoré", "embedded_type": "network"},
    ]
}
