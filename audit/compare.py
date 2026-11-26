"""Common-input repair comparison for the audit branch. All measurements use the returned triangles."""
from __future__ import annotations

import collections
import hashlib
import importlib.metadata as metadata
import json
import logging
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import time
import traceback

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests/python"))
from meshgen import cube, concat, sphere

TOOLS = ("meshfix", "pymeshfix-default", "pymeshfix-keep", "trimesh")
CASES = {}


def add(name, mesh, bodies, volume):
    v, f = mesh
    CASES[name] = np.asarray(v, dtype="<f8"), np.asarray(f, dtype="<i4"), bodies, volume


def fixtures():
    v, f = cube()
    add("cube", (v, f), 1, 1)
    add("triangle-hole", (v, f[1:]), 1, 1)
    add("quad-hole", (v, f[2:]), 1, 1)
    flipped = f.copy()
    flipped[[1, 4, 8]] = flipped[[1, 4, 8], ::-1]
    add("inconsistent-winding", (v, flipped), 1, 1)
    add("inverted", (v, f[:, ::-1]), 1, 1)
    add("duplicate-face", (v, np.vstack((f, f[0]))), 1, 1)
    add("degenerate-face", (v, np.vstack((f, [0, 0, 1]))), 1, 1)
    add("stl-soup", (v[f].reshape(-1, 3), np.arange(f.size).reshape(-1, 3)), 1, 1)
    midpoint = (v[0] + v[1]) / 2
    tj = np.vstack((np.delete(f, 4, axis=0), [0, 8, 5], [8, 1, 5]))
    add("t-junction", (np.vstack((v, midpoint)), tj), 1, 1)
    # Hexagonal prism missing the entire (six-edge) lid. Bottom and sides still define the outline.
    ring = np.array([(math.cos(i*math.pi/3), math.sin(i*math.pi/3)) for i in range(6)])
    prism = np.vstack((np.c_[ring, np.zeros(6)], np.c_[ring, np.ones(6)], [0, 0, 0]))
    sides = []
    for i in range(6):
        j = (i + 1) % 6
        sides.extend(([12, j, i], [i, j, j+6], [i, j+6, i+6]))
    add("hexagonal-hole", (prism, sides), 1, 1.5*math.sqrt(3))
    add("disjoint-two", concat(cube(), cube(.5, (2, 0, 0))), 2, 1.125)
    add("nested-cavity", concat(cube(), cube(.5, (.25,)*3)), 2, .875)
    add("touching-edge", concat(cube(), cube(1, (1, 1, 0))), 2, 2)
    add("touching-vertex", concat(cube(), cube(1, (1, 1, 1))), 2, 2)
    off = (.37, .43, .29)
    add("interpenetrating", concat(cube(), cube(1, off)), 1, 2-np.prod(1-np.array(off)))
    tet = (np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1]]), [[0,2,1],[0,1,3],[0,3,2],[1,2,3]])
    add("valid-tetrahedron", tet, 1, 1/6)
    add("translated-cube", (v + 1e7, f), 1, 1)
    add("tiny-cube", (v * 1e-6, f), 1, 1e-18)
    add("large-cube", (v * 1e5, f), 1, 1e15)
    if (Path("Avocado.glb")).exists():
        import trimesh
        model = trimesh.load_scene("Avocado.glb", process=False).to_geometry()
        p, t = np.asarray(model.vertices), np.asarray(model.faces)
        # Fixed corruption; reference is the independently measured, unmodified source.
        ref = inspect(p, t)
        add("avocado", (p, t), ref["components"], ref["volume"])
        add("avocado-missing-face", (p, t[1:]), ref["components"], ref["volume"])


def groups(adj):
    seen = set()
    result = []
    for node in adj:
        if node in seen:
            continue
        todo = [node]
        seen.add(node)
        group = []
        while todo:
            current = todo.pop()
            group.append(current)
            for other in adj[current]:
                if other not in seen:
                    seen.add(other)
                    todo.append(other)
        result.append(group)
    return result


def proper_crossings(v, f):
    # Independent segment/triangle test, normalized per model. Strict interiors only.
    if len(f) > 100:
        return None
    v = v - v.min(axis=0)
    v /= np.max(np.ptp(v, axis=0)) or 1
    count = 0
    for i, a in enumerate(f):
        for b in f[:i]:
            if set(a) & set(b):
                continue
            crosses = False
            for tri, other in ((a, b), (b, a)):
                p, q, r = v[other]
                u, w = q-p, r-p
                for ix in range(3):
                    start, end = v[tri[ix]], v[tri[(ix+1)%3]]
                    d = end - start
                    h = np.cross(d, w)
                    det = np.dot(u, h)
                    if abs(det) < 1e-13:
                        continue
                    s = start - p
                    h2 = np.cross(s, u)
                    x = np.dot(s, h)/det
                    y = np.dot(d, h2)/det
                    t = np.dot(w, h2)/det
                    if min(x, y, 1-x-y, t, 1-t) > 1e-9:
                        crosses = True
                        break
                if crosses:
                    break
            count += crosses
    return count


def inspect(vertices, faces):
    v = np.asarray(vertices, float).reshape(-1, 3)
    f = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    if not len(f):
        return dict(faces=0, closed=False, manifold=False, components=0, volume=0., crossings=0)
    if not np.isfinite(v).all() or f.min() < 0 or f.max() >= len(v):
        raise ValueError("invalid result vertices or indices")
    v, remap = np.unique(v, axis=0, return_inverse=True)
    f = remap[f]
    edges = collections.defaultdict(list)
    incident = collections.defaultdict(set)
    adj = {i: set() for i in range(len(f))}
    fans = collections.defaultdict(lambda: collections.defaultdict(set))
    for i, (a,b,c) in enumerate(f.tolist()):
        for u,w in ((a,b),(b,c),(c,a)):
            edges[tuple(sorted((u,w)))].append((i, u<w))
            incident[u].add(i)
            fans[u][i]
    for (u,w), uses in edges.items():
        ids = {i for i,_ in uses}
        for i in ids:
            adj[i].update(ids)
            fans[u][i].update(ids)
            fans[w][i].update(ids)
    parts = groups(adj)
    volumes = []
    for part in parts:
        xyz = v[f[part]]
        a,b,c = np.moveaxis(xyz-xyz[0,0],1,0)
        volumes.append(float(np.einsum("ij,ij->i", a, np.cross(b,c)).sum()/6))
    t = v[f]
    ar = np.linalg.norm(np.cross(t[:,1]-t[:,0], t[:,2]-t[:,0]),axis=1)
    boundary = sum(len(e)==1 for e in edges.values())
    over = sum(len(e)>2 for e in edges.values())
    wrong = sum(len(e)==2 and e[0][1]==e[1][1] for e in edges.values())
    badfans = sum(len(groups(fan))>1 for fan in fans.values())
    return dict(faces=len(f), vertices=len(v), components=len(parts), volume=sum(volumes),
                shell_volumes=sorted(volumes), boundary=boundary, nonmanifold_edges=over,
                winding_errors=wrong, multi_fan_vertices=badfans, degenerate=int((ar==0).sum()),
                closed=not (boundary or over or wrong), manifold=not (over or badfans),
                crossings=proper_crossings(v, f))


def hash_mesh(v, f):
    v, f = np.asarray(v, dtype="<f8"), np.asarray(f, dtype="<i4")
    h = hashlib.sha256()
    for a in (v,f):
        h.update(struct.pack("<Q", a.size))
        h.update(a.tobytes())
    return h.hexdigest()


def fit(tool, v, f):
    if tool == "meshfix":
        import meshfix
        p, t, rep = meshfix.repair(v, f)
        return p, t, rep.to_dict()
    if tool.startswith("pymeshfix"):
        import pymeshfix
        m = pymeshfix.MeshFix(v.copy(), f.copy())
        if tool == "pymeshfix-keep":
            m.repair(remove_smallest_components=False)
        else:
            m.repair()
        return m.points, m.faces, {}
    import trimesh
    m = trimesh.Trimesh(v.copy(), f.copy(), process=False)
    m.process(validate=True)
    trimesh.repair.fill_holes(m)
    trimesh.repair.fix_normals(m, multibody=True)
    return m.vertices, m.faces, {}


def worker(tool, path, dest):
    data = np.load(path)
    v, f = data["v"], data["f"]
    # Warm import. Durations exclude import and checker cost; per-call smoke numbers only.
    __import__("pymeshfix" if tool.startswith("pymeshfix") else tool)
    start = time.perf_counter()
    p, t, report = fit(tool, v, f)
    runtime = time.perf_counter()-start
    result = dict(hash=hash_mesh(p,t), native=report, seconds=runtime, measured=inspect(p,t))
    p2,t2,_ = fit(tool, v, f)
    result["repeat_bytes"] = hash_mesh(p2,t2) == result["hash"]
    if len(t):
        p3,t3,_ = fit(tool, np.array(p), np.array(t))
        result["second_pass_bytes"] = hash_mesh(p3,t3) == result["hash"]
        result["second_pass"] = inspect(p3,t3)
    Path(dest).write_text(json.dumps(result), encoding="utf8")


def suite():
    out = Path("audit-output")
    out.mkdir(exist_ok=True)
    fd, logfile = tempfile.mkstemp(prefix="meshfix-audit-", suffix=".log")
    os.close(fd)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                        handlers=[logging.FileHandler(logfile), logging.StreamHandler()])
    logging.info("Log %s", logfile)
    try:
        fixtures()
        results = {"packages":{p:metadata.version(p) for p in ("pymeshfix","trimesh","numpy","scipy","networkx")},
                   "python":sys.version,"sha":os.environ.get("GITHUB_SHA"),"fixtures":{},"rows":[]}
        for name, (v,f,components,volume) in CASES.items():
            casefile = out / (name + ".npz")
            np.savez(casefile, v=v, f=f)
            results["fixtures"][name] = {"input_hash":hash_mesh(v,f),"input":inspect(v,f),
                                         "target_components":components,"target_volume":volume}
            for tool in TOOLS:
                row = {"tool":tool, "case":name}
                target = out / (name+"--"+tool+".json")
                try:
                    proc = subprocess.run([sys.executable,__file__,"worker",tool,str(casefile),str(target)],
                                          capture_output=True, text=True, timeout=40)
                    if proc.returncode:
                        raise RuntimeError(f"exit {proc.returncode}: {(proc.stdout+proc.stderr)[-900:]}")
                    row.update(json.loads(target.read_text()))
                    m = row["measured"]
                    row["geometry_pass"] = bool(m["faces"] and m["closed"] and m["manifold"]
                        and not m.get("degenerate") and m["crossings"] in (None,0)
                        and m["components"]==components and abs(m["volume"]-volume)<=1e-3*abs(volume))
                except Exception as exc:
                    row["error"] = str(exc)
                logging.info("%s %s %s", name, tool, row.get("error",row.get("geometry_pass")))
                results["rows"].append(row)
                (out/"results.json").write_text(json.dumps(results, indent=2))
        # Distinguish harness execution from mesh quality. Geometry failures are the comparison data.
        if not all(any("measured" in r for r in results["rows"] if r["tool"]==t) for t in TOOLS):
            raise RuntimeError("at least one adapter produced no measurements")
    finally:
        logging.info("Log %s", logfile)
        (out/"audit.log").write_bytes(Path(logfile).read_bytes())


if __name__ == "__main__":
    if len(sys.argv)>1:
        worker(*sys.argv[2:])
    else:
        suite()
