#!/usr/bin/env python3
"""GeoJSON-seq (osmium export) -> компактные части ukr2022 (NDJSON.gz, ≤45 МБ).
Строка: [класс, id, имя, геометрия, флаги]; геометрия — целые 1e-5° (первая точка абсолютно, далее приращения);
полигон: {"o":[кольца], "i":[дыры]}; мультиполигон — несколько таких строк с одним id."""
import gzip, io, json, math, sys

src, prefix, snapshot = sys.argv[1], sys.argv[2], sys.argv[3]
BUILDINGS = '--buildings' in sys.argv
LIMIT = 45 * 1024 * 1024

def classify(t, gtype):
    h = t.get('highway')
    if h:
        if h.startswith(('motorway', 'trunk')): return 'r1'
        if h.startswith('primary'): return 'r2'
        if h.startswith('secondary'): return 'r3'
        if h.startswith('tertiary'): return 'r4'
        if h in ('unclassified', 'residential', 'living_street', 'road', 'pedestrian'): return 'r5'
        if h == 'service': return 'r6'
        if h == 'track': return 'r7'
        return None
    if t.get('place') in ('city', 'town', 'village', 'hamlet') and gtype == 'Point': return 'place'
    rw = t.get('railway')
    if rw in ('station', 'halt'): return 'station' if gtype == 'Point' else None
    if rw == 'tram': return 'tram'
    if rw: return 'rail'
    if t.get('aeroway') == 'runway': return 'runway'
    if t.get('aeroway') == 'aerodrome': return 'aerodrome'
    if t.get('man_made') == 'bridge': return 'bridgearea'
    n, lu, ww = t.get('natural'), t.get('landuse'), t.get('waterway')
    if n == 'coastline': return 'coast'
    if n == 'tree_row': return 'treerow'
    if lu == 'forest' or n == 'wood': return 'forest'
    if n == 'scrub': return 'scrub'
    if n == 'wetland': return 'wet'
    if n == 'water' or ww == 'riverbank' or (t.get('water') and gtype != 'LineString'): return 'water'
    if ww in ('river', 'canal', 'stream', 'ditch'): return 'w_' + ww
    if ww == 'dam': return 'dam'
    if n in ('beach', 'sand'): return 'sand'
    if lu == 'military': return 'mil'
    if lu in ('industrial', 'railway', 'garages'): return 'ind'
    if lu in ('residential', 'retail', 'commercial'): return 'urban'
    if lu == 'farmyard': return 'farm'
    if lu == 'cemetery': return 'cem'
    if lu in ('orchard', 'vineyard'): return 'orch'
    return None

TOL = {'r1': 1e-5, 'r2': 1e-5, 'r3': 1e-5, 'r4': 1.5e-5, 'r5': 1.5e-5, 'r6': 2e-5, 'r7': 3e-5, 'rail': 1e-5, 'tram': 2e-5,
       'treerow': 3e-5, 'coast': 1e-5, 'dam': 1e-5, 'w_river': 1.5e-5, 'w_canal': 1.5e-5, 'w_stream': 3e-5, 'w_ditch': 3e-5, 'bld': 1e-5}

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

def enc(pts):
    out, px, py = [], 0, 0
    for i, (x, y) in enumerate(pts):
        X, Y = round(x * 1e5), round(y * 1e5)
        out += [X, Y] if i == 0 else [X - px, Y - py]; px, py = X, Y
    return out

class Parts:
    def __init__(self, prefix): self.prefix, self.n, self.buf, self.raw = prefix, 0, None, None; self.open()
    def open(self):
        self.n += 1; self.raw = io.BytesIO(); self.buf = gzip.GzipFile(fileobj=self.raw, mode='wb', compresslevel=9)
        self.buf.write((json.dumps({'format': 'ukr2022-osm-v1', 'snapshot': snapshot, 'note': '© OpenStreetMap contributors, ODbL'}) + '\n').encode())
    def write(self, line):
        self.buf.write((line + '\n').encode())
        if self.raw.tell() > LIMIT: self.close(); self.open()
    def close(self):
        self.buf.close(); open(f'{self.prefix}_part{self.n}.json.gz', 'wb').write(self.raw.getvalue())

from collections import Counter
cnt = Counter(); parts = Parts(prefix)
with open(src, encoding='utf-8') as f:
    for line in f:
        line = line.strip().lstrip('\x1e')
        if not line: continue
        ft = json.loads(line); g = ft.get('geometry'); p = ft.get('properties', {})
        if not g: continue
        gtype = g['type']
        cls = 'bld' if BUILDINGS else classify(p, gtype)
        if not cls: continue
        oid = (p.get('@type', 'x')[0]) + str(p.get('@id', ''))
        name = ''
        if cls in ('r1', 'r2', 'r3', 'r4', 'r5', 'station', 'rail', 'place', 'w_river', 'w_canal', 'water', 'aerodrome'):
            name = ' '.join(x for x in (p.get('ref'), p.get('name:uk') or p.get('name')) if x)
            if cls == 'place': name = json.dumps([p.get('name:uk') or p.get('name') or '', p.get('name:ru') or '', p.get('place'), p.get('population') or ''], ensure_ascii=False)
        flags = ('b' if p.get('bridge') not in (None, 'no') else '') + ('t' if p.get('tunnel') not in (None, 'no') else '')
        if BUILDINGS: flags = p.get('building') if p.get('building') not in (None, 'yes') else ''
        tol = TOL.get(cls, 3e-5)
        if gtype == 'Point': geoms = [enc([g['coordinates']])]
        elif gtype == 'LineString': geoms = [enc(dp(g['coordinates'], tol))]
        elif gtype in ('Polygon', 'MultiPolygon'):
            polys = [g['coordinates']] if gtype == 'Polygon' else g['coordinates']
            geoms = [{'o': [enc(dp(poly[0], tol))], 'i': [enc(dp(r, tol)) for r in poly[1:]]} for poly in polys]
        else: continue
        for gm in geoms:
            parts.write(json.dumps([cls, oid, name, gm, flags], ensure_ascii=False, separators=(',', ':')))
            cnt[cls] += 1
parts.close()
print(prefix, dict(cnt))
