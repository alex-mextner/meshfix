"""Deterministic bidirectional sampled surface distance, normalized by the intact reference diagonal."""
from __future__ import annotations

import numpy as np


def samples(triangles):
    # All vertices and centroids of small models. On larger models include fixed subsets of both.
    rng = np.random.default_rng(842713)
    verts = np.unique(triangles.reshape(-1, 3), axis=0)
    verts = verts[rng.choice(len(verts), min(len(verts), 64), replace=False)]
    centroids = triangles.mean(axis=1)
    centroids = centroids[rng.choice(len(centroids), min(len(centroids), 64), replace=False)]
    areas = np.linalg.norm(np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0]), axis=1)
    if areas.sum() == 0:
        return np.vstack((verts, centroids))
    ts = triangles[rng.choice(len(triangles), 128, p=areas/areas.sum())]
    u, v = rng.random((2,len(ts)))
    reflect = (u+v>1)
    u[reflect], v[reflect] = 1-u[reflect], 1-v[reflect]
    pts = ts[:,0]+u[:,None]*(ts[:,1]-ts[:,0])+v[:,None]*(ts[:,2]-ts[:,0])
    return np.vstack((verts, centroids, pts))


def closest(points, triangles):
    # Project onto the triangle plane if barycentric coordinates are inside; otherwise use the three segments.
    a,b,c = np.moveaxis(triangles, 1, 0)
    u,w = b-a,c-a
    inner = lambda x,y: np.einsum("ij,ij->i",x,y)
    uu,uw,ww = inner(u,u),inner(u,w),inner(w,w)
    denom = uu*ww-uw*uw
    good = denom>0
    normals = np.cross(u,w)
    nn = inner(normals,normals)
    distances = []
    segments = [(start,stop-start,inner(stop-start,stop-start)) for start,stop in ((a,b),(b,c),(c,a))]
    for p in points:
        d = p-a
        du,dw = inner(d,u),inner(d,w)
        x = np.divide(ww*du-uw*dw,denom,out=np.zeros_like(denom),where=good)
        y = np.divide(uu*dw-uw*du,denom,out=np.zeros_like(denom),where=good)
        valid = good & (x>=0) & (y>=0) & (x+y<=1)
        sq = np.divide(inner(d,normals)**2, nn, out=np.full_like(nn,np.inf),where=valid & (nn>0))
        for start,vec,length2 in segments:
            delta = p-start
            t = np.divide(inner(delta,vec),length2,out=np.zeros_like(length2),where=length2>0).clip(0,1)
            diff = delta - t[:,None]*vec
            sq = np.minimum(sq,inner(diff,diff))
        distances.append(float(np.sqrt(sq.min())))
    return np.asarray(distances)


def surface(reference_vertices, reference_faces, actual_vertices, actual_faces):
    if not len(reference_faces) or not len(actual_faces):
        return None
    vr, va = np.asarray(reference_vertices),np.asarray(actual_vertices)
    lo = vr.min(axis=0)
    hi = vr.max(axis=0)
    diag = np.linalg.norm(hi-lo)
    if not diag:
        return None
    fr, fa = np.asarray(reference_faces,int),np.asarray(actual_faces,int)
    rt = ((vr-lo)/diag)[fr]
    at = ((va-lo)/diag)[fa]
    missing = closest(samples(rt),at)
    excess = closest(samples(at),rt)
    return {"ref_to_output_max":float(missing.max()), "output_to_ref_max":float(excess.max()),
            "bidirectional_p95":float(np.quantile(np.r_[missing,excess],.95)),
            "bbox_linf":float(np.max(np.abs(np.r_[lo-va.min(axis=0),hi-va.max(axis=0)]))/diag),
            "sample_count":len(missing)+len(excess)}
