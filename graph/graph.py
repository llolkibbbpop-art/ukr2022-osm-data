#!/usr/bin/env python3
"""Дорожный граф юга Украины из OSM (снимок 01.01.2022) для поиска пути в игре.
Узлы — перекрёстки и концы дорог (по идентификаторам узлов OSM, связность точная).
Рёбра — участки дорог между узлами: [a, b, класс, длина_м, мост(0/1), геометрия (целые 1e-5° с приращениями, без концов)].
Классы: 1 магистраль/trunk, 2 primary, 3 secondary, 4 tertiary, 5 unclassified/residential/road/living_street, 7 track (1-2 сорт)."""
import gzip, json, math, sys
import osmium

SRC, OUT = sys.argv[1], sys.argv[2]
CLS = {'motorway': 1, 'trunk': 1, 'motorway_link': 1, 'trunk_link': 1, 'primary': 2, 'primary_link': 2,
       'secondary': 3, 'secondary_link': 3, 'tertiary': 4, 'tertiary_link': 4,
       'unclassified': 5, 'residential': 5, 'road': 5, 'living_street': 5, 'track': 7}

class H(osmium.SimpleHandler):
    def __init__(self):
        super().__init__(); self.ways = []; self.use = {}
    def way(self, w):
        h = w.tags.get('highway')
        c = CLS.get(h)
        if not c: return
        if c == 7 and w.tags.get('tracktype') in ('grade3', 'grade4', 'grade5'): return   # плохие грунтовки — это «поле»
        try: pts = [(n.ref, n.lon, n.lat) for n in w.nodes]
        except osmium.InvalidLocationError: return
        if len(pts) < 2: return
        b = 1 if w.tags.get('bridge') not in (None, 'no') else 0
        self.ways.append((c, b, pts))
        for i, (ref, _, _) in enumerate(pts):
            self.use[ref] = self.use.get(ref, 0) + (2 if i in (0, len(pts) - 1) else 1)

h = H(); h.apply_file(SRC, locations=True)
print('ways', len(h.ways))

def hav(a, b):
    lat = math.radians((a[1] + b[1]) / 2)
    return math.hypot((b[0] - a[0]) * 111320 * math.cos(lat), (b[1] - a[1]) * 110574)

def dp(pts, eps):
    n = len(pts)
    if n < 3: return pts
    keep = [False] * n; keep[0] = keep[-1] = True; st = [(0, n - 1)]
    while st:
        a, b = st.pop(); x1, y1 = pts[a]; x2, y2 = pts[b]; dx, dy = x2 - x1, y2 - y1; L = math.hypot(dx, dy); best, idx = eps, -1
        for i in range(a + 1, b):
            x, y = pts[i]
            d = abs(dy * x - dx * y + x2 * y1 - y2 * x1) / L if L > 1e-12 else math.hypot(x - x1, y - y1)
            if d > best: best, idx = d, i
        if idx > 0: keep[idx] = True; st += [(a, idx), (idx, b)]
    return [p for p, k in zip(pts, keep) if k]

nid, nodes, edges = {}, [], []
def node(ref, lon, lat):
    if ref not in nid: nid[ref] = len(nodes); nodes.append((round(lon * 1e5), round(lat * 1e5)))
    return nid[ref]
for c, b, pts in h.ways:
    start = 0
    for i in range(1, len(pts)):
        if h.use[pts[i][0]] >= 2 or i == len(pts) - 1:
            seg = pts[start:i + 1]
            a = node(*seg[0]); z = node(*seg[-1])
            ll = [(p[1], p[2]) for p in seg]
            L = sum(hav(p, q) for p, q in zip(ll, ll[1:]))
            mid = dp(ll, 0.00004)[1:-1]          # ~4 м
            g, px, py = [], nodes[a][0], nodes[a][1]
            for x, y in mid:
                X, Y = round(x * 1e5), round(y * 1e5); g += [X - px, Y - py]; px, py = X, Y
            if a != z or L > 5: edges.append([a, z, c, round(L), b, g])
            start = i
print('nodes', len(nodes), 'edges', len(edges))
flat = []
px = py = 0
for x, y in nodes: flat += [x - px, y - py]; px, py = x, y
data = json.dumps({'format': 'ukr2022-graph-v1', 'note': '© OpenStreetMap contributors, ODbL', 'nodes': flat, 'edges': edges}, separators=(',', ':'))
with gzip.open(OUT, 'wt', encoding='utf-8', compresslevel=9) as f: f.write(data)
import os; print('size', os.path.getsize(OUT))
