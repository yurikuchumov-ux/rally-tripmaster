"""Строит маршрут по дорожной книге на дорогах OpenStreetMap.

    python3 tools/route.py legend.txt roads.json LAT LON out_dir

legend.txt — формат вкладки «Легенда» (км | выезд | дороги | действие | инфо).
roads.json — выгрузка Overpass (way[highway] + узлы) вокруг старта.

Идём от старта по дорогам: между пунктами книги на неупомянутых перекрёстках
едем «прямо» (поворот меньше STRAIGHT), на пункте книги ищем перекрёсток
на нужном расстоянии и выезд под нужным углом. Держим лучших BEAM вариантов.
"""
import json, math, sys, os, html
sys.setrecursionlimit(50000)

STRAIGHT = 40      # град: неупомянутый перекрёсток проезжаем, если дорога идёт почти прямо
ANGLE_TOL = 50     # град: допуск угла выезда на пункте книги
BEAM = 40


def hav(a, b):
    R = 6371000.0
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    s = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(s))


def bearing(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    y = math.sin(lo2 - lo1) * math.cos(la2)
    x = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(lo2 - lo1)
    return math.degrees(math.atan2(y, x)) % 360


def turn(a, b):  # угол поворота с курса a на курс b: + направо
    return (b - a + 540) % 360 - 180


def parse_legend(path):
    head, pts = {}, []
    for line in open(path, encoding="utf8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        f = [s.strip() for s in line.split("|")]
        if line.startswith("@"):
            head = {"title": f[0][1:].strip(), "len": float(f[1].replace(",", "."))}
            continue
        t = f[0].split()
        km = float(t[-1].replace(",", "."))
        ex = float(f[1]) if len(f) > 1 and f[1] else 0.0
        pts.append({"n": t[0] if len(t) > 1 else str(len(pts) + 1), "km": km, "exit": ex,
                    "act": f[3] if len(f) > 3 else "", "flags": (f[2] if len(f) > 2 else "").split()})
    pts.sort(key=lambda p: p["km"])
    return head, pts


def load_graph(path):
    d = json.load(open(path))
    pos = {e["id"]: (e["lat"], e["lon"]) for e in d["elements"] if e["type"] == "node"}
    out, und = {}, {}
    for w in (e for e in d["elements"] if e["type"] == "way"):
        nd = [n for n in w["nodes"] if n in pos]
        ow = w.get("tags", {}).get("oneway")
        for a, b in zip(nd, nd[1:]):
            und.setdefault(a, set()).add(b); und.setdefault(b, set()).add(a)
            if ow != "-1":
                out.setdefault(a, set()).add(b)
            if ow not in ("yes", "1", "true"):
                out.setdefault(b, set()).add(a)
    return pos, out, und


def head_of(pos, a, b, back=False):
    """Курс по участку a→b, сглаженный: берём точку ~15 м по дуге, а не соседний узел."""
    return bearing(pos[a], pos[b])


def walk(pos, out, und, prev, cur, dist, lo, hi, want_exit, path, found, depth=0, seen=None):
    """Ехать от cur (въехали из prev), пока dist <= hi; на подходящих узлах в окне [lo, hi] записать кандидатов."""
    if dist > hi or depth > 4000:
        return
    seen = {} if seen is None else seen
    if seen.get((prev, cur), 1e18) <= dist:   # сюда уже приезжали не длиннее — дальше то же самое
        return
    seen[(prev, cur)] = dist
    nxt = [n for n in out.get(cur, ()) if n != prev]
    hin = bearing(pos[prev], pos[cur])
    is_junction = len(und.get(cur, ())) >= 3
    if dist >= lo and (is_junction or abs(want_exit) < 15):
        for n in nxt:
            t = turn(hin, bearing(pos[cur], pos[n]))
            err = abs(turn(want_exit, t))
            if err <= ANGLE_TOL:
                found.append((err, dist, prev, cur, n, path))
    if not nxt:
        return
    if is_junction:
        opts = [n for n in nxt if abs(turn(hin, bearing(pos[cur], pos[n]))) < STRAIGHT]
        if not opts and (len(nxt) == 1 or os.environ.get("LOOSE")):
            opts = nxt                     # дорога изгибается; LOOSE — на парковках «прямо» нет, пробуем все
    else:
        opts = nxt
    for n in (opts if os.environ.get("LOOSE") else opts[:2]):
        walk(pos, out, und, cur, n, dist + hav(pos[cur], pos[n]), lo, hi, want_exit, path + [n], found, depth + 1, seen)


def solve(pos, out, und, start, pts):
    near = sorted(pos, key=lambda n: hav(pos[n], start))[:6]
    # старт: стоим на ближайшем узле дороги, едем в любую сторону
    states = []
    for s in near:
        if hav(pos[s], start) > 150:
            continue
        for n in out.get(s, ()):
            states.append({"score": hav(pos[s], start) / 50, "prev": s, "cur": n,
                           "dist": hav(pos[s], pos[n]), "path": [s, n], "marks": [(pts[0], s, 0.0, 0.0)]})
    for i in range(1, len(pts)):
        p, d = pts[i], (pts[i]["km"] - pts[i - 1]["km"]) * 1000
        tol = max(float(os.environ.get("TOL_M", 40)), float(os.environ.get("TOL_P", 0.07)) * d)
        nxt_states = []
        for st in states:
            found = []
            walk(pos, out, und, st["prev"], st["cur"], st["dist"], d - tol, d + tol, p["exit"], [], found)
            for err, dist, prev, cur, n, path in found:
                nxt_states.append({
                    "score": st["score"] + err / ANGLE_TOL + abs(dist - d) / tol,
                    "prev": cur, "cur": n, "dist": hav(pos[cur], pos[n]),
                    "path": st["path"] + path + [n],
                    "marks": st["marks"] + [(p, cur, dist - d, err)]})
        if not nxt_states:
            return states, i            # дальше пункт i не нашёлся
        nxt_states.sort(key=lambda s: s["score"])
        uniq, seen = [], set()
        for s in nxt_states:
            k = (s["prev"], s["cur"])
            if k not in seen:
                seen.add(k); uniq.append(s)
        states = uniq[:BEAM]
    return states, len(pts)


def main():
    leg, roads, lat, lon, out_dir = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), sys.argv[5]
    head, pts = parse_legend(leg)
    pos, out, und = load_graph(roads)
    states, reached = solve(pos, out, und, (lat, lon), pts)
    os.makedirs(out_dir, exist_ok=True)
    if not states:
        print("Старт не найден рядом с дорогой"); return
    best = states[0]
    coords = [pos[n] for n in best["path"]]
    report = []
    for p, node, derr, aerr in best["marks"]:
        report.append(f"п.{p['n']:>3} км {p['km']:6.2f}  {p['act'][:34]:34}  расст. {derr:+5.0f} м  угол ±{aerr:3.0f}°  {pos[node][0]:.6f},{pos[node][1]:.6f}")
    alt = len(states)
    print(f"Найдено пунктов: {reached} из {len(pts)}; вариантов на последнем шаге: {alt}")
    if reached < len(pts):
        print(f"Не нашёлся п.{pts[reached]['n']} (км {pts[reached]['km']:.2f}) — дальше маршрут не строится")
    print("\n".join(report))

    # GPX: трек + точки пунктов книги
    g = ['<?xml version="1.0" encoding="UTF-8"?>', '<gpx version="1.1" creator="rally-tripmaster" xmlns="http://www.topografix.com/GPX/1/1">']
    for p, node, _, _ in best["marks"]:
        g.append(f'<wpt lat="{pos[node][0]}" lon="{pos[node][1]}"><name>п.{html.escape(p["n"])} км {p["km"]:.2f}</name><desc>{html.escape(p["act"])}</desc></wpt>')
    g.append(f'<trk><name>{html.escape(head.get("title", "Маршрут"))}</name><trkseg>')
    g += [f'<trkpt lat="{a}" lon="{b}"/>' for a, b in coords]
    g += ['</trkseg></trk>', '</gpx>']
    open(os.path.join(out_dir, "route.gpx"), "w", encoding="utf8").write("\n".join(g))

    marks = [{"n": p["n"], "km": p["km"], "act": p["act"], "ll": pos[node], "derr": round(derr), "aerr": round(aerr)}
             for p, node, derr, aerr in best["marks"]]
    page = open(os.path.join(os.path.dirname(__file__), "map_template.html"), encoding="utf8").read()
    page = page.replace("/*DATA*/", "const ROUTE=" + json.dumps(coords) + ";const MARKS=" + json.dumps(marks, ensure_ascii=False)
                        + ";const START=" + json.dumps([lat, lon]) + ";const TITLE=" + json.dumps(head.get("title", ""), ensure_ascii=False) + ";")
    open(os.path.join(out_dir, "route.html"), "w", encoding="utf8").write(page)
    print("Готово:", os.path.join(out_dir, "route.gpx"), os.path.join(out_dir, "route.html"))


if __name__ == "__main__":
    main()
