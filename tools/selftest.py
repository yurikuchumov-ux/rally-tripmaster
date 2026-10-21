"""Самопроверка route.py: случайный маршрут по OSM от старта -> легенда с шумом -> эталон.

    python3 tools/selftest.py tools roads.json LAT LON leg.txt truth.json SEED

import json, math, random, sys
sys.path.insert(0, sys.argv[1])
import route as R

roads, lat, lon, out_leg, out_truth, seed = sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), sys.argv[5], sys.argv[6], int(sys.argv[7])
random.seed(seed)
pos, out, und = R.load_graph(roads)
d = json.load(open(roads))
hw = {}
for w in (e for e in d["elements"] if e["type"] == "way"):
    for n in w["nodes"]:
        hw.setdefault(n, set()).add(w["tags"].get("highway"))
MAIN = {"tertiary", "secondary", "unclassified", "residential", "primary", "trunk"}

s = min(pos, key=lambda n: R.hav(pos[n], (lat, lon)))
prev, cur = s, random.choice(sorted(out[s]))
path, km, legend = [s, cur], R.hav(pos[s], pos[cur]), [(0.0, 0, [])]
seen = {s, cur}
while km < 9000:
    nxt = [n for n in out.get(cur, ()) if n != prev and n not in seen]
    if not nxt:
        break
    hin = R.bearing(pos[prev], pos[cur])
    turns = {n: R.turn(hin, R.bearing(pos[cur], pos[n])) for n in nxt}
    if len(und.get(cur, ())) >= 3:
        good = [n for n in nxt if hw.get(n, set()) & MAIN] or nxt
        n = random.choice(good)
        t = turns[n]
        others = [round(R.turn(hin, R.bearing(pos[cur], pos[m]))) for m in und[cur] if m not in (prev, n)]
        straight_alts = [m for m in nxt if m != n and abs(turns[m]) < R.STRAIGHT]
        # в книгу попадает поворот или развилка, где «прямо» неоднозначно
        if abs(t) >= R.STRAIGHT or straight_alts:
            legend.append((km, t, others))
    else:
        n = nxt[0]
    km += R.hav(pos[cur], pos[n])
    prev, cur = cur, n
    path.append(n); seen.add(n)

with open(out_leg, "w", encoding="utf8") as f:
    f.write(f"@ ТЕСТ Курово | {km/1000:.2f} | 45 | 00:12\n")
    for i, (m, t, oth) in enumerate(legend):
        dk = m * random.uniform(0.98, 1.02) / 1000
        ang = round(t + random.uniform(-10, 10)) if i else 0
        f.write(f"{i+1} {dk:.2f} | {ang} | {' '.join(map(str, oth))} | {'направо' if ang > 20 else 'налево' if ang < -20 else 'прямо'} | \n")
json.dump([pos[n] for n in path], open(out_truth, "w"))
print(f"эталон: {km/1000:.2f} км, пунктов в книге: {len(legend)}")
