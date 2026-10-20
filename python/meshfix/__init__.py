"""meshfix: triangle mesh repair. Same shape as the C API (include/meshfix.h).

    import meshfix
    vertices, faces, report = meshfix.repair(vertices, faces)
    report = meshfix.repair_file("in.stl", "out.stl")

SPDX-License-Identifier: MIT
"""
from __future__ import annotations

import array
import ctypes
import enum
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Callable, Optional, Sequence, Union

from . import _native
from ._native import LibraryNotFound

__version__ = "0.1.0"
__all__ = [
    "Fix",
    "Options",
    "Report",
    "MeshfixError",
    "LibraryNotFound",
    "repair",
    "repair_file",
    "analyze",
    "version",
    "abi_version",
    "__version__",
]

try:  # numpy is optional: without it meshes are lists of tuples
    import numpy as _np
except ImportError:  # pragma: no cover - exercised by the pure-python test
    _np = None

_lib = _native.lib


class Fix(enum.IntFlag):
    """Which repairs run (meshfix_options.flags). Same values as MESHFIX_FIX_* / MESHFIX_CHECK_*."""

    NONE = 0
    WELD = 1 << 0
    DEGENERATE = 1 << 1
    DUPLICATE_FACES = 1 << 2
    T_JUNCTIONS = 1 << 3
    ORIENTATION = 1 << 4
    NON_MANIFOLD = 1 << 5
    HOLES = 1 << 6
    COMPONENTS = 1 << 7
    NESTED_SHELLS = 1 << 8
    SEPARATE = 1 << 9
    ALL = 0x3FF
    CHECK_SELF_INTERSECTIONS = 1 << 16


ProgressCallback = Callable[[str, float], bool]


@dataclass
class Options:
    """meshfix_options. `progress(stage, fraction)` may return True to cancel."""

    flags: int = int(Fix.ALL | Fix.CHECK_SELF_INTERSECTIONS)
    weld_tolerance: float = -1.0  # < 0 auto, 0 exact merge only
    max_hole_edges: int = 0  # 0 no limit
    min_component_faces: int = 8
    separation: float = -1.0  # < 0 auto
    progress: Optional[ProgressCallback] = field(default=None, compare=False)


@dataclass
class Report:
    """meshfix_report. Verdicts are bool (self_intersections_remain: None when not checked)."""

    watertight_before: bool = False
    watertight_after: bool = False
    manifold_before: bool = False
    manifold_after: bool = False
    self_intersections_remain: Optional[bool] = None
    input_vertices: int = 0
    input_faces: int = 0
    output_vertices: int = 0
    output_faces: int = 0
    vertices_merged: int = 0
    invalid_faces_removed: int = 0
    degenerate_faces_removed: int = 0
    duplicate_faces_removed: int = 0
    t_junctions_fixed: int = 0
    faces_flipped: int = 0
    non_manifold_edges_before: int = 0
    non_manifold_edges_after: int = 0
    non_manifold_vertices_split: int = 0
    boundary_edges_before: int = 0
    boundary_edges_after: int = 0
    holes_found: int = 0
    holes_filled: int = 0
    holes_skipped: int = 0
    hole_faces_added: int = 0
    components_before: int = 0
    components_after: int = 0
    small_components_removed: int = 0
    flat_components_removed: int = 0
    cavity_shells: int = 0
    self_intersecting_pairs: int = 0
    volume_before: float = 0.0
    volume_after: float = 0.0
    weld_tolerance_used: float = 0.0
    elapsed_ms: float = 0.0
    vertices_separated: int = 0

    # Aliases some callers (3d-cli prep) key on.
    @property
    def faces_before(self) -> int:
        return self.input_faces

    @property
    def faces_after(self) -> int:
        return self.output_faces

    @property
    def vertices_before(self) -> int:
        return self.input_vertices

    @property
    def vertices_after(self) -> int:
        return self.output_vertices

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.update(
            faces_before=self.faces_before,
            faces_after=self.faces_after,
            vertices_before=self.vertices_before,
            vertices_after=self.vertices_after,
        )
        return d

    @classmethod
    def _from_c(cls, c: _native.CReport) -> "Report":
        values: dict[str, Any] = {}
        for f in fields(cls):
            raw = getattr(c, f.name)
            if f.name == "self_intersections_remain":
                values[f.name] = None if raw < 0 else bool(raw)
            elif f.name in ("watertight_before", "watertight_after", "manifold_before", "manifold_after"):
                values[f.name] = bool(raw)
            else:
                values[f.name] = raw
        return cls(**values)


class MeshfixError(RuntimeError):
    """A meshfix call failed; `status` is the MESHFIX_ERR_* code."""

    def __init__(self, status: int, message: str):
        super().__init__(f"{_lib.meshfix_status_string(status).decode()}: {message}" if message else
                         _lib.meshfix_status_string(status).decode())
        self.status = status


def _check(status: int) -> None:
    if status != 0:
        raise MeshfixError(status, (_lib.meshfix_last_error() or b"").decode(errors="replace"))


def version() -> str:
    return _lib.meshfix_version().decode()


def abi_version() -> int:
    return int(_lib.meshfix_abi_version())


# ---------------------------------------------------------------- conversions

ArrayLike = Union[Sequence[Sequence[float]], Any]


def _flat_doubles(vertices: ArrayLike) -> tuple[Any, int]:
    if _np is not None:
        a = _np.ascontiguousarray(vertices, dtype=_np.float64)
        if a.ndim != 2 or a.shape[1] != 3:
            raise ValueError("vertices must have shape (N, 3)")
        return a, a.shape[0]
    buf = array.array("d")
    n = 0
    for v in vertices:
        if len(v) != 3:
            raise ValueError("vertices must be a sequence of (x, y, z)")
        buf.extend(float(c) for c in v)
        n += 1
    return buf, n


def _flat_indices(faces: ArrayLike, vertex_count: int) -> tuple[Any, int]:
    if _np is not None:
        a = _np.asarray(faces)
        if a.size == 0:
            a = a.reshape(0, 3)
        if a.ndim != 2 or a.shape[1] != 3:
            raise ValueError("faces must have shape (M, 3)")
        if a.dtype.kind not in "iu":
            raise ValueError("faces must be integer vertex indices")
        if a.size and (a.min() < 0 or a.max() > 0xFFFFFFFF):
            raise ValueError("face indices must be in 0 .. 2**32-1")
        a = _np.ascontiguousarray(a, dtype=_np.uint32)
        return a, a.shape[0]
    buf = array.array("I")
    n = 0
    for f in faces:
        if len(f) != 3:
            raise ValueError("faces must be a sequence of (a, b, c)")
        for i in f:
            if i < 0:
                raise ValueError("face indices must be non-negative")
        buf.extend(int(i) for i in f)
        n += 1
    return buf, n


def _address(buf: Any) -> Optional[int]:
    if _np is not None and isinstance(buf, _np.ndarray):
        return buf.ctypes.data if buf.size else None
    if len(buf) == 0:
        return None
    return buf.buffer_info()[0]


class _Mesh:
    """Owns a meshfix_mesh handle."""

    def __init__(self, handle: ctypes.c_void_p):
        self.handle = handle

    @classmethod
    def from_arrays(cls, vertices: ArrayLike, faces: ArrayLike) -> "_Mesh":
        v, nv = _flat_doubles(vertices)
        f, nf = _flat_indices(faces, nv)
        handle = ctypes.c_void_p()
        _check(_lib.meshfix_mesh_create(_address(v), nv, _address(f), nf, ctypes.byref(handle)))
        return cls(handle)

    def to_arrays(self) -> tuple[Any, Any]:
        nv = _lib.meshfix_mesh_vertex_count(self.handle)
        nf = _lib.meshfix_mesh_face_count(self.handle)
        vp = _lib.meshfix_mesh_vertices(self.handle)
        fp = _lib.meshfix_mesh_faces(self.handle)
        if _np is not None:
            v = _np.ctypeslib.as_array(vp, shape=(nv * 3,)).reshape(nv, 3).copy() if nv else _np.zeros((0, 3))
            f = (
                _np.ctypeslib.as_array(fp, shape=(nf * 3,)).reshape(nf, 3).astype(_np.uint32, copy=True)
                if nf
                else _np.zeros((0, 3), dtype=_np.uint32)
            )
            return v, f
        vs = [tuple(vp[3 * i : 3 * i + 3]) for i in range(nv)]
        fs = [tuple(fp[3 * i : 3 * i + 3]) for i in range(nf)]
        return vs, fs

    def __del__(self) -> None:
        handle = getattr(self, "handle", None)
        if handle is not None and handle.value:
            _lib.meshfix_mesh_free(handle)
            handle.value = None


def _coptions(options: Optional[Options], overrides: dict[str, Any]) -> tuple[_native.COptions, Any]:
    opts = options if options is not None else Options()
    if overrides:
        unknown = set(overrides) - {f.name for f in fields(Options)}
        if unknown:
            raise TypeError(f"unknown option(s): {', '.join(sorted(unknown))}")
        opts = Options(**{**{f.name: getattr(opts, f.name) for f in fields(Options)}, **overrides})
    c = _native.COptions()
    _lib.meshfix_options_init(ctypes.byref(c))
    c.flags = int(opts.flags)
    c.weld_tolerance = float(opts.weld_tolerance)
    c.max_hole_edges = int(opts.max_hole_edges)
    c.min_component_faces = int(opts.min_component_faces)
    c.separation = float(opts.separation)
    keepalive = None
    if opts.progress is not None:
        user = opts.progress

        def trampoline(_user: Any, stage: bytes, fraction: float) -> int:
            try:
                return 1 if user(stage.decode(), fraction) else 0
            except BaseException:  # an exception must not unwind through C: cancel instead
                trampoline.error = True  # type: ignore[attr-defined]
                return 1

        trampoline.error = False  # type: ignore[attr-defined]
        keepalive = _native.PROGRESS_FN(trampoline)
        c.progress = keepalive
    return c, keepalive


def repair(
    vertices: ArrayLike,
    faces: ArrayLike,
    options: Optional[Options] = None,
    **overrides: Any,
) -> tuple[Any, Any, Report]:
    """Repair a triangle mesh. vertices (N, 3) floats, faces (M, 3) vertex indices.

    Returns (vertices, faces, report): float64 (N, 3) / uint32 (M, 3) numpy arrays (lists of tuples without
    numpy). Keyword overrides set Options fields, e.g. repair(v, f, max_hole_edges=500)."""
    mesh = _Mesh.from_arrays(vertices, faces)
    copts, _keep = _coptions(options, overrides)
    creport = _native.CReport()
    _lib.meshfix_report_init(ctypes.byref(creport))
    out = ctypes.c_void_p()
    _check(_lib.meshfix_repair(mesh.handle, ctypes.byref(copts), ctypes.byref(out), ctypes.byref(creport)))
    result = _Mesh(out)
    v, f = result.to_arrays()
    return v, f, Report._from_c(creport)


def analyze(vertices: ArrayLike, faces: ArrayLike, options: Optional[Options] = None, **overrides: Any) -> Report:
    """Inspect a mesh without repairing it (the *_after fields mirror *_before). `options` is accepted for parity
    with the C API; analysis currently reads none of them."""
    mesh = _Mesh.from_arrays(vertices, faces)
    copts, _keep = _coptions(options, overrides)
    creport = _native.CReport()
    _lib.meshfix_report_init(ctypes.byref(creport))
    _check(_lib.meshfix_analyze(mesh.handle, ctypes.byref(copts), ctypes.byref(creport)))
    return Report._from_c(creport)


def repair_file(
    src: Union[str, "os.PathLike[str]"],
    dst: Union[str, "os.PathLike[str]", None] = None,
    options: Optional[Options] = None,
    **overrides: Any,
) -> Report:
    """Read an .stl/.obj, repair it and write dst (.stl/.obj) when given."""
    import os

    handle = ctypes.c_void_p()
    _check(_lib.meshfix_mesh_read(os.fsencode(src), ctypes.byref(handle)))
    mesh = _Mesh(handle)
    copts, _keep = _coptions(options, overrides)
    creport = _native.CReport()
    _lib.meshfix_report_init(ctypes.byref(creport))
    out = ctypes.c_void_p()
    _check(_lib.meshfix_repair(mesh.handle, ctypes.byref(copts), ctypes.byref(out), ctypes.byref(creport)))
    result = _Mesh(out)
    if dst is not None:
        _check(_lib.meshfix_mesh_write(result.handle, os.fsencode(dst)))
    return Report._from_c(creport)
