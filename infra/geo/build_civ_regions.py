"""Construit le fond de carte des régions de Côte d'Ivoire pour l'interface (tracés SVG précalculés).

Source : geoBoundaries, CIV ADM2 (33 unités : 31 régions + 2 districts autonomes), données Banque mondiale 2016,
licence CC BY 4.0 — attribution affichée sous la carte.
  https://github.com/wmgeolab/geoBoundaries/raw/9469f09/releaseData/gbOpen/CIV/ADM2/geoBoundaries-CIV-ADM2_simplified.geojson

Usage : python infra/geo/build_civ_regions.py <geojson> frontend/lib/geo/civRegions.json
Projection équirectangulaire corrigée de la latitude moyenne (suffisante à cette échelle), simplification
Douglas-Peucker, coordonnées arrondies : ~40 Ko au lieu de ~750 Ko.
"""

import json
import math
import sys

CODES = {
    "Agneby-Tiassa": "AGNEBY_TIASSA",
    "Bafing": "BAFING",
    "Bagoue": "BAGOUE",
    "Belier": "BELIER",
    "Bere": "BERE",
    "Bounkani": "BOUNKANI",
    "Cavally": "CAVALLY",
    "District Autonome D'Abidjan": "ABIDJAN",
    "District Autonome De Yamoussoukro": "YAMOUSSOUKRO",
    "Folon": "FOLON",
    "Gbeke": "GBEKE",
    "Gbokle": "GBOKLE",
    "Goh": "GOH",
    "Gontougo": "GONTOUGO",
    "Grands Ponts": "GRANDS_PONTS",
    "Guemon": "GUEMON",
    "Hambol": "HAMBOL",
    "Haut-Sassandra": "HAUT_SASSANDRA",
    "Iffou": "IFFOU",
    "Indenie-Djuablin": "INDENIE_DJUABLIN",
    "Kabadougou": "KABADOUGOU",
    "Loh-Djiboua": "LOH_DJIBOUA",
    "Marahoue": "MARAHOUE",
    "Me": "LA_ME",
    "Nawa": "NAWA",
    "Poro": "PORO",
    "San Pedro": "SAN_PEDRO",
    "Sud-Comoe": "SUD_COMOE",
    "Tchologo": "TCHOLOGO",
    "Tonkpi": "TONKPI",
    "Worodougou": "WORODOUGOU",
    "N'Zi": "NZI",
    "Moronou": "MORONOU",
}
WIDTH = 560
TOLERANCE = 0.012  # degrés


def simplify(points, tolerance):
    if len(points) < 4:
        return points

    def distance(p, a, b):
        if a == b:
            return math.dist(p, a)
        (x, y), (x1, y1), (x2, y2) = p, a, b
        return abs((y2 - y1) * x - (x2 - x1) * y + x2 * y1 - y2 * x1) / math.dist(a, b)

    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        start, end = stack.pop()
        best, index = 0.0, None
        for i in range(start + 1, end):
            d = distance(points[i], points[start], points[end])
            if d > best:
                best, index = d, i
        if index is not None and best > tolerance:
            keep[index] = True
            stack += [(start, index), (index, end)]
    return [p for p, k in zip(points, keep) if k]


def rings(geometry):
    polygons = (
        geometry["coordinates"]
        if geometry["type"] == "MultiPolygon"
        else [geometry["coordinates"]]
    )
    return [
        polygon[0] for polygon in polygons
    ]  # contours extérieurs (pas de trous significatifs à cette échelle)


def area_centroid(ring):
    a = cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        cross = x1 * y2 - x2 * y1
        a += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    a /= 2
    return abs(a), (cx / (6 * a), cy / (6 * a)) if a else ring[0]


def main(source, target):
    data = json.load(open(source, encoding="utf-8"))
    all_points = [p for f in data["features"] for r in rings(f["geometry"]) for p in r]
    lons = [p[0] for p in all_points]
    lats = [p[1] for p in all_points]
    k = math.cos(math.radians((min(lats) + max(lats)) / 2))
    scale = WIDTH / ((max(lons) - min(lons)) * k)
    height = round((max(lats) - min(lats)) * scale)

    def project(p):
        return round((p[0] - min(lons)) * k * scale, 1), round(
            (max(lats) - p[1]) * scale, 1
        )

    regions = []
    for feature in data["features"]:
        name = feature["properties"]["shapeName"]
        code = CODES[name]
        parts, best = [], (0, None)
        for ring in rings(feature["geometry"]):
            projected = [project(p) for p in simplify(ring, TOLERANCE)]
            parts.append("M" + "L".join(f"{x:g},{y:g}" for x, y in projected) + "Z")
            area, centroid = area_centroid(projected)
            if area > best[0]:
                best = (area, centroid)
        cx, cy = best[1]
        regions.append(
            {
                "code": code,
                "path": "".join(parts),
                "cx": round(cx, 1),
                "cy": round(cy, 1),
            }
        )
    regions.sort(key=lambda r: r["code"])
    out = {
        "width": WIDTH,
        "height": height,
        "attribution": "Limites administratives : geoBoundaries (CIV ADM2), Banque mondiale 2016, CC BY 4.0",
        "regions": regions,
    }
    json.dump(
        out,
        open(target, "w", encoding="utf-8"),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    unused = set(CODES.values()) - {r["code"] for r in regions}
    assert not unused, unused
    print(f"{len(regions)} unités, {WIDTH}×{height}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
