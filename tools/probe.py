"""Подбор трудного пункта вручную: доезжаем по книге до пункта K и печатаем все перекрёстки
в окне вокруг расстояния до следующего пункта — с углами выездов и названиями улиц.

    START_BEARING=165 python3 tools/probe.py legend.txt roads.json LAT LON K [окно_м]
"""
import json, sys, os
sys.path.insert(0, os.path.dirname(__file__))
import route as R

leg, roads, lat, lon, k = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), sys.argv[5]
win = float(sys.argv[6]) if len(sys.argv) > 6 else 200
head, pts = R.parse_legend(leg)
idx = [p["n"] for p in pts].index(k)
pos, out, und = R.load_graph(roads)
d = json.load(open(roads))
name = {}
for w in (e for e in d["elements"] if e["type"] == "way"):
    t = w.get("tags", {})
    for n in w["nodes"]:
        name.setdefault(n, set()).add((t.get("name") or t.get("ref") or "") + "/" + t.get("highway", ""))
states, reached = R.solve(pos, out, und, (lat, lon), pts[:idx + 1])
nxt = pts[idx + 1]
dd = (nxt["km"] - pts[idx]["km"]) * 1000
print(f"дошли до п.{k}: {reached == idx + 1}; вариантов {len(states)}; ищем п.{nxt['n']} через {dd:.0f} м, выезд {nxt['exit']:+.0f}° ({nxt['act']})")
R.ANGLE_TOL = 180
seen = set()
for si, st in enumerate(states[:5]):
    found = []
    R.walk(pos, out, und, st["prev"], st["cur"], st["dist"], dd - win, dd + win, 0, [], found)
    for err, dist, prev, cur, n, path in sorted(found, key=lambda f: f[1]):
        if (cur, n) in seen:
            continue
        seen.add((cur, n))
        t = R.turn(R.bearing(pos[prev], pos[cur]), R.bearing(pos[cur], pos[n]))
        print(f"  вар{si} {dist:6.0f} м  выезд {t:+5.0f}°  узел {cur} {pos[cur][0]:.6f},{pos[cur][1]:.6f}  {sorted(name.get(cur, []))[:3]}")
