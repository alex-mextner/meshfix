"""Generated test meshes (no files, no third-party data)."""
from __future__ import annotations

import numpy as np

CUBE_V = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], float)
CUBE_F = np.array([[0, 3, 2], [0, 2, 1], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4],
                   [3, 7, 6], [3, 6, 2], [0, 4, 7], [0, 7, 3], [1, 2, 6], [1, 6, 5]], np.uint32)


def cube(size=1.0, origin=(0, 0, 0)):
    return CUBE_V * size + np.asarray(origin, float), CUBE_F.copy()


def sphere(radius=1.0, levels=2, center=(0, 0, 0)):
    t = (1 + 5 ** 0.5) / 2
    v = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t),
         (0, -1, -t), (0, 1, -t), (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
    v = [np.array(p, float) / np.linalg.norm(p) for p in v]
    f = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6),
         (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10),
         (8, 6, 7), (9, 8, 1)]
    for _ in range(levels):
        mid = {}

        def midpoint(a, b):
            key = (min(a, b), max(a, b))
            if key not in mid:
                p = (v[a] + v[b]) / 2
                v.append(p / np.linalg.norm(p))
                mid[key] = len(v) - 1
            return mid[key]

        nf = []
        for a, b, c in f:
            ab, bc, ca = midpoint(a, b), midpoint(b, c), midpoint(c, a)
            nf += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
        f = nf
    return np.array(v) * radius + np.asarray(center, float), np.array(f, np.uint32)


def concat(a, b):
    return np.vstack([a[0], b[0]]), np.vstack([a[1], b[1] + len(a[0])]).astype(np.uint32)


def flip_all(m):
    return m[0], m[1][:, ::-1].copy()


def drop_faces(m, idx):
    keep = np.ones(len(m[1]), bool)
    keep[list(idx)] = False
    return m[0], m[1][keep]


def volume(m):
    v, f = m
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6)
