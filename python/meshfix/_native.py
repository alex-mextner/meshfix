"""ctypes binding of the meshfix C ABI (include/meshfix.h). No compiled Python extension: one wheel per platform
serves every Python version, and any build of libmeshfix with the same ABI version works.

SPDX-License-Identifier: MIT
"""
from __future__ import annotations

import ctypes
import ctypes.util
import os
import sys
from ctypes import (
    CFUNCTYPE,
    POINTER,
    Structure,
    c_char_p,
    c_double,
    c_int,
    c_int32,
    c_size_t,
    c_uint32,
    c_uint64,
    c_void_p,
)
from pathlib import Path

ABI_VERSION = 1

PROGRESS_FN = CFUNCTYPE(c_int, c_void_p, c_char_p, c_double)


class COptions(Structure):
    _fields_ = [
        ("struct_size", c_uint32),
        ("flags", c_uint32),
        ("weld_tolerance", c_double),
        ("max_hole_edges", c_uint32),
        ("min_component_faces", c_uint32),
        ("progress", PROGRESS_FN),
        ("progress_user", c_void_p),
        ("separation", c_double),
    ]


# (name, ctypes type) in the order of struct meshfix_report; the counters are uint64 and the verdicts int32.
REPORT_INT32 = (
    "watertight_before",
    "watertight_after",
    "manifold_before",
    "manifold_after",
    "self_intersections_remain",
    "reserved0",
    "reserved1",
)
REPORT_COUNTERS = (
    "input_vertices",
    "input_faces",
    "output_vertices",
    "output_faces",
    "vertices_merged",
    "invalid_faces_removed",
    "degenerate_faces_removed",
    "duplicate_faces_removed",
    "t_junctions_fixed",
    "faces_flipped",
    "non_manifold_edges_before",
    "non_manifold_edges_after",
    "non_manifold_vertices_split",
    "boundary_edges_before",
    "boundary_edges_after",
    "holes_found",
    "holes_filled",
    "holes_skipped",
    "hole_faces_added",
    "components_before",
    "components_after",
    "small_components_removed",
    "flat_components_removed",
    "cavity_shells",
    "self_intersecting_pairs",
)
REPORT_DOUBLES = ("volume_before", "volume_after", "weld_tolerance_used", "elapsed_ms")
REPORT_TRAILING = ("vertices_separated",)


class CReport(Structure):
    _fields_ = (
        [("struct_size", c_uint32)]
        + [(n, c_int32) for n in REPORT_INT32]
        + [(n, c_uint64) for n in REPORT_COUNTERS]
        + [(n, c_double) for n in REPORT_DOUBLES]
        + [(n, c_uint64) for n in REPORT_TRAILING]
    )


class LibraryNotFound(ImportError):
    pass


def _candidates() -> list[Path | str]:
    env = os.environ.get("MESHFIX_LIBRARY")
    here = Path(__file__).resolve().parent
    names = {
        "linux": ["libmeshfix.so"],
        "darwin": ["libmeshfix.dylib"],
        "win32": ["meshfix.dll", "libmeshfix.dll"],
    }.get(sys.platform if sys.platform in ("darwin", "win32") else "linux", ["libmeshfix.so"])
    out: list[Path | str] = []
    if env:
        out.append(env)
    out += [here / n for n in names]
    # A source checkout: python/meshfix/ -> <repo>/build
    root = here.parent.parent
    for sub in ("build", "build/Release", "build/Debug"):
        out += [root / sub / n for n in names]
    return out


def _load() -> ctypes.CDLL:
    tried = []
    for cand in _candidates():
        path = Path(cand)
        tried.append(str(path))
        if path.is_file():
            if sys.platform == "win32" and hasattr(os, "add_dll_directory"):
                os.add_dll_directory(str(path.parent))
            return ctypes.CDLL(str(path))
    found = ctypes.util.find_library("meshfix")
    if found:
        return ctypes.CDLL(found)
    raise LibraryNotFound(
        "libmeshfix not found. Install the wheel (pip install meshfix), build it (cmake -S . -B build && "
        "cmake --build build) or set MESHFIX_LIBRARY=/path/to/libmeshfix. Looked in: " + ", ".join(tried)
    )


lib = _load()

lib.meshfix_abi_version.restype = c_uint32
if lib.meshfix_abi_version() != ABI_VERSION:
    raise LibraryNotFound(
        f"libmeshfix ABI {lib.meshfix_abi_version()} does not match this Python package (ABI {ABI_VERSION})"
    )

_mesh_p = c_void_p
lib.meshfix_version.restype = c_char_p
lib.meshfix_status_string.restype = c_char_p
lib.meshfix_status_string.argtypes = [c_int]
lib.meshfix_last_error.restype = c_char_p
lib.meshfix_options_init.argtypes = [POINTER(COptions)]
lib.meshfix_report_init.argtypes = [POINTER(CReport)]
lib.meshfix_mesh_create.argtypes = [c_void_p, c_size_t, c_void_p, c_size_t, POINTER(_mesh_p)]
lib.meshfix_mesh_create.restype = c_int
lib.meshfix_mesh_create_f32.argtypes = [c_void_p, c_size_t, c_void_p, c_size_t, POINTER(_mesh_p)]
lib.meshfix_mesh_create_f32.restype = c_int
lib.meshfix_mesh_free.argtypes = [_mesh_p]
lib.meshfix_mesh_vertex_count.argtypes = [_mesh_p]
lib.meshfix_mesh_vertex_count.restype = c_size_t
lib.meshfix_mesh_face_count.argtypes = [_mesh_p]
lib.meshfix_mesh_face_count.restype = c_size_t
lib.meshfix_mesh_vertices.argtypes = [_mesh_p]
lib.meshfix_mesh_vertices.restype = POINTER(c_double)
lib.meshfix_mesh_faces.argtypes = [_mesh_p]
lib.meshfix_mesh_faces.restype = POINTER(c_uint32)
lib.meshfix_mesh_read.argtypes = [c_char_p, POINTER(_mesh_p)]
lib.meshfix_mesh_read.restype = c_int
lib.meshfix_mesh_write.argtypes = [_mesh_p, c_char_p]
lib.meshfix_mesh_write.restype = c_int
lib.meshfix_repair.argtypes = [_mesh_p, POINTER(COptions), POINTER(_mesh_p), POINTER(CReport)]
lib.meshfix_repair.restype = c_int
lib.meshfix_analyze.argtypes = [_mesh_p, POINTER(COptions), POINTER(CReport)]
lib.meshfix_analyze.restype = c_int
lib.meshfix_report_to_json.argtypes = [POINTER(CReport), c_char_p, c_size_t]
lib.meshfix_report_to_json.restype = c_size_t

__all__ = ["lib", "COptions", "CReport", "PROGRESS_FN", "LibraryNotFound"]
