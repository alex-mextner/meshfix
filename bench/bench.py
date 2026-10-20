#!/usr/bin/env python3
"""Benchmark: repair a mesh file, or a generated defective sphere, and print before/after proof.

    python bench/bench.py model.stl                 # any STL / OBJ
    python bench/bench.py --synthetic 7             # icosphere level 7 (327,680 faces) with injected defects

With trimesh installed, the result is also checked by a second implementation (trimesh merges equal vertices
and counts edges itself), so the watertight verdict does not rest on meshfix's own report.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
import meshfix  # noqa: E402


def icosphere(levels: int):
    t = (1 + 5 ** 0.5) / 2
    v = np.array([(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t),
                  (0, -1, -t), (0, 1, -t), (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)], float)
    v /= np.linalg.norm(v, axis=1)[:, None]
    f = np.array([(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2),
                  (10, 7, 6), (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5),
                  (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1)], np.int64)
    for _ in range(levels):
        edges = np.sort(np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]]), axis=1)
        uniq, inv = np.unique(edges, axis=0, return_inverse=True)
        mid = v[uniq[:, 0]] + v[uniq[:, 1]]
        mid /= np.linalg.norm(mid, axis=1)[:, None]
        n = len(f)
        ab, bc, ca = (inv[:n] + len(v)), (inv[n:2 * n] + len(v)), (inv[2 * n:] + len(v))
        v = np.vstack([v, mid])
        a, b, c = f[:, 0], f[:, 1], f[:, 2]
        f = np.concatenate([np.stack([a, ab, ca], 1), np.stack([b, bc, ab], 1), np.stack([c, ca, bc], 1),
                            np.stack([ab, bc, ca], 1)])
    return v, f


def defective_sphere(levels: int, seed: int = 1):
    """A unit sphere as an STL-style soup with noisy duplicate vertices, holes, flipped faces, duplicate faces."""
    rng = np.random.default_rng(seed)
    v, f = icosphere(levels)
    nf = len(f)
    f = f.copy()
    flip = rng.choice(nf, nf // 200, replace=False)
    f[flip] = f[flip][:, ::-1]
    keep = np.ones(nf, bool)
    for centre in rng.choice(nf, 12, replace=False):  # twelve holes: a face and its neighbours by vertex
        near = np.where((f == f[centre][0]).any(axis=1))[0]
        keep[near] = False
    dup = rng.choice(np.where(keep)[0], nf // 500, replace=False)
    f = np.concatenate([f[keep], f[dup]])
    soup = v[f].reshape(-1, 3) + rng.uniform(-1e-7, 1e-7, (len(f) * 3, 3))
    return soup, np.arange(len(soup), dtype=np.uint32).reshape(-1, 3)


def load(path: str):
    # Read through the library itself: meshfix_mesh_read merges equal vertices like any STL consumer.
    handle = meshfix._native.ctypes.c_void_p()
    meshfix._check(meshfix._native.lib.meshfix_mesh_read(os.fsencode(path), meshfix._native.ctypes.byref(handle)))
    return meshfix._Mesh(handle).to_arrays()


def trimesh_verdict(v, f):
    try:
        import trimesh
    except ImportError:
        return None
    m = trimesh.Trimesh(v, f, process=True)  # merges vertices, drops nothing else
    return {"watertight": bool(m.is_watertight), "winding_consistent": bool(m.is_winding_consistent),
            "is_volume": bool(m.is_volume), "volume": float(m.volume) if m.is_volume else None}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", nargs="?")
    ap.add_argument("--synthetic", type=int, metavar="LEVELS", help="icosphere subdivision level (7 = 327,680 faces)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if bool(args.file) == (args.synthetic is not None):
        ap.error("give a file or --synthetic LEVELS")
    if args.synthetic is not None and args.synthetic < 3:
        ap.error("--synthetic needs LEVELS >= 3 (the injected defects need at least 1,280 faces)")

    if args.synthetic is not None:
        v, f = defective_sphere(args.synthetic)
        label = f"synthetic icosphere level {args.synthetic}"
    else:
        v, f = load(args.file)
        label = os.path.basename(args.file)

    before = trimesh_verdict(v, f)
    t0 = time.perf_counter()
    out_v, out_f, report = meshfix.repair(v, f)
    wall = time.perf_counter() - t0
    after = trimesh_verdict(out_v, out_f)

    summary = {
        "mesh": label,
        "faces_before": report.input_faces, "faces_after": report.output_faces,
        "watertight_before": report.watertight_before, "watertight_after": report.watertight_after,
        "volume_before": report.volume_before, "volume_after": report.volume_after,
        "repair_seconds": round(report.elapsed_ms / 1000, 3), "wall_seconds_incl_marshalling": round(wall, 3),
        "report": report.to_dict(),
        "trimesh_before": before, "trimesh_after": after,
    }
    if args.json:
        print(json.dumps(summary, indent=2))
        return 0
    print(f"{label}: {report.input_faces} -> {report.output_faces} faces in {report.elapsed_ms / 1000:.2f} s")
    print(f"  watertight  {report.watertight_before} -> {report.watertight_after}")
    print(f"  volume      {report.volume_before:.6g} -> {report.volume_after:.6g}")
    print(f"  holes filled {report.holes_filled}, non-manifold edges {report.non_manifold_edges_before} -> "
          f"{report.non_manifold_edges_after}, faces flipped {report.faces_flipped}, duplicate faces removed "
          f"{report.duplicate_faces_removed}, vertices merged {report.vertices_merged}")
    if before is not None:
        print(f"  trimesh says: watertight {before['watertight']} -> {after['watertight']}, "
              f"volume {before['volume']} -> {after['volume']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
