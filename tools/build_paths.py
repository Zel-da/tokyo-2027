"""ROUTES 각 구간의 실제 경로를 계산해 paths.json 으로 저장한다.

- 전철·지하철: OpenStreetMap 선로(rail.json, Overpass)로 그래프를 만들고 역→경유역→역 순서로 최단 경로
- 도보: routing.openstreetmap.de (OSRM foot) 실제 보행 경로
- 자동차: routing.openstreetmap.de (OSRM car)
- 비행기: 대권 곡선 근사

사용: python tools/build_paths.py routes.json rail.json paths.json
"""
import heapq, json, math, sys, time, urllib.request

routes_f, rail_f, out_f = sys.argv[1:4]
D = json.load(open(routes_f, encoding="utf8"))
C, ROUTES = D["C"], D["ROUTES"]


def hav(a, b):
    r = math.pi / 180
    dlat, dlon = (b[0] - a[0]) * r, (b[1] - a[1]) * r
    h = math.sin(dlat / 2) ** 2 + math.cos(a[0] * r) * math.cos(b[0] * r) * math.sin(dlon / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


# ---- 선로 그래프
rail = json.load(open(rail_f, encoding="utf8"))["elements"]
pos, adj = {}, {}
for w in rail:
    ns, gs = w.get("nodes", []), w.get("geometry", [])
    for n, g in zip(ns, gs):
        pos[n] = (g["lat"], g["lon"])
    for a, b in zip(ns, ns[1:]):
        if a in pos and b in pos:
            d = hav(pos[a], pos[b])
            adj.setdefault(a, []).append((b, d))
            adj.setdefault(b, []).append((a, d))
nodes = list(adj)
# 간단한 격자 인덱스
cell = {}
for n in nodes:
    k = (round(pos[n][0] / 0.005), round(pos[n][1] / 0.005))
    cell.setdefault(k, []).append(n)


def near(p, radius=450):
    k0 = (round(p[0] / 0.005), round(p[1] / 0.005))
    out = []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for n in cell.get((k0[0] + dx, k0[1] + dy), []):
                d = hav(p, pos[n])
                if d <= radius:
                    out.append((d, n))
    return out


def rail_leg(a, b):
    src, dst = near(a), {n: d for d, n in near(b)}
    if not src or not dst:
        return None
    dist, prev, pq = {}, {}, []
    for d, n in src:
        dist[n] = d
        heapq.heappush(pq, (d, n))
    best, bestn = float("inf"), None
    while pq:
        d, n = heapq.heappop(pq)
        if d > dist.get(n, 1e18) or d >= best:
            continue
        if n in dst and d + dst[n] < best:
            best, bestn = d + dst[n], n
        for m, w in adj[n]:
            nd = d + w
            if nd < dist.get(m, 1e18):
                dist[m], prev[m] = nd, n
                heapq.heappush(pq, (nd, m))
    if bestn is None or best > 4 * hav(a, b) + 2000:
        return None
    path, n = [], bestn
    while n in prev:
        path.append(pos[n])
        n = prev[n]
    path.append(pos[n])
    path.reverse()
    return [list(a)] + [list(p) for p in path] + [list(b)]


def osrm(profile, a, b):
    u = (f"https://routing.openstreetmap.de/routed-{profile}/route/v1/driving/"
         f"{a[1]},{a[0]};{b[1]},{b[0]}?overview=full&geometries=geojson")
    for _ in range(3):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "trip-map-builder/1.0"}), timeout=30))
            rt = r["routes"][0]
            return [[c[1], c[0]] for c in rt["geometry"]["coordinates"]], rt["distance"], rt["duration"]
        except Exception as e:  # 잠시 후 재시도
            time.sleep(2)
    return None


def simplify(pts, tol=6):
    """Douglas-Peucker (미터 단위 근사)."""
    if len(pts) < 3:
        return pts
    def perp(p, a, b):
        ax, ay = a[1] * 90000, a[0] * 111000
        bx, by = b[1] * 90000, b[0] * 111000
        px, py = p[1] * 90000, p[0] * 111000
        dx, dy = bx - ax, by - ay
        if dx == dy == 0:
            return math.hypot(px - ax, py - ay)
        t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        return math.hypot(px - ax - t * dx, py - ay - t * dy)
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        dmax, k = 0, 0
        for m in range(i + 1, j):
            d = perp(pts[m], pts[i], pts[j])
            if d > dmax:
                dmax, k = d, m
        if dmax > tol:
            keep[k] = True
            stack += [(i, k), (k, j)]
    return [[round(p[0], 6), round(p[1], 6)] for p, f in zip(pts, keep) if f]


def arc(a, b, n=40):
    mid = [(a[0] + b[0]) / 2 + abs(a[1] - b[1]) * 0.12, (a[1] + b[1]) / 2]
    return [[(1 - t) ** 2 * a[0] + 2 * (1 - t) * t * mid[0] + t * t * b[0],
             (1 - t) ** 2 * a[1] + 2 * (1 - t) * t * mid[1] + t * t * b[1]] for t in (i / n for i in range(n + 1))]


OUT, report = {}, []
for day, R in ROUTES.items():
    segs = []
    for i in range(1, len(R)):
        st, pv = R[i], R[i - 1]
        a, b = C[pv["p"]], C[st["p"]]
        mode = st.get("m", "walk")
        pts, meters, secs, how = None, None, None, "straight"
        if mode in ("train", "subway"):
            chain = [a] + [C[v] for v in st.get("v", [])] + [b]
            pts, ok = [], True
            for x, y in zip(chain, chain[1:]):
                leg = rail_leg(x, y)
                if leg is None:
                    ok = False
                    leg = [list(x), list(y)]
                pts += leg if not pts else leg[1:]
            how = "rail" if ok else "rail(partial)"
        elif mode == "walk":
            if hav(a, b) < 15:
                pts = [a, b]
            else:
                r = osrm("foot", a, b)
                if r:
                    pts, meters, secs = r
                    pts = [list(a)] + pts + [list(b)]
                    how = "foot"
                time.sleep(1)
        elif mode == "car":
            r = osrm("car", a, b)
            if r:
                pts, meters, secs = r
                how = "car"
            time.sleep(1)
        elif mode == "plane":
            pts, how = arc(a, b), "arc"
        if not pts:
            pts = [a, b]
        if meters is None:
            meters = sum(hav(p, q) for p, q in zip(pts, pts[1:]))
        segs.append({"c": simplify(pts) if mode != "plane" else [[round(x, 5), round(y, 5)] for x, y in pts],
                     "m": round(meters), "s": round(secs) if secs else None})
        report.append(f"{day} {pv['s']}→{st['s']} [{mode}] {how} {round(meters)}m pts={len(segs[-1]['c'])}")
    OUT[day] = segs

json.dump(OUT, open(out_f, "w", encoding="utf8"), separators=(",", ":"))
print("\n".join(report))
