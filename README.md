# meshfix

Fast, deterministic triangle-mesh repair for 3D printing. A C++17 core with **no dependencies** (no CGAL, no
libslic3r, no Boost), a **stable C ABI**, Python bindings of the same shape, and a command line tool.

It takes the kind of mesh a marketplace STL or a scan really is - open holes, flipped faces, doubled and
near-doubled vertices, edges shared by four faces, T-junctions, floating specks - and returns a closed,
consistently oriented mesh a slicer accepts, with a report that proves what changed.

```
$ meshfix model.stl -o fixed.stl      # a 411k-face marketplace STL, see Benchmarks
faces            411213 -> 411110
watertight       no -> yes
manifold         no -> yes
volume           78151.5 -> 78151.5
boundary edges   37 -> 0
non-manifold e.  87 -> 0 (vertex copies 60)
removed faces    invalid 0, degenerate 0, duplicate 100
flipped faces    16
holes            found 19, filled 19, skipped 0 (+37 faces)
components       1 -> 1 (small removed 13, flat removed 0, cavities 0)
time             1532.1 ms
```

Used by [3d-cli](https://github.com/alex-mextner/3d-cli) (`3d mesh --repair`) and by the
[Snapmaker Orca fork](https://github.com/alex-mextner/SnapOrca) ("Fix model", through the C ABI).

## What it repairs

| Stage (flag) | Fixes |
|---|---|
| `WELD` | coincident and near-coincident vertices (exact merge, then within a tolerance; STL "soups" become indexed meshes) |
| `DEGENERATE` | zero-area faces, faces with a repeated vertex (also what welding collapses) |
| `DUPLICATE_FACES` | the same face twice; back-to-back pairs (a zero-thickness sheet) cancel |
| `T_JUNCTIONS` | a vertex lying on a neighbour's edge (cracks from non-conforming subdivision): the edge's face is split |
| `ORIENTATION` | inconsistent winding is made consistent, every closed shell points outward |
| `NON_MANIFOLD` | edges with 3+ faces are paired radially and split; vertices where several fans touch are split into one vertex per fan |
| `HOLES` | boundary loops are filled: minimum-area triangulation for small holes, ear clipping for larger ones, a centroid fan as the always-valid fallback; pinched loops are handled loop by loop |
| `COMPONENTS` | islands with fewer than `min_component_faces` faces and closed shells without volume are dropped |
| `NESTED_SHELLS` | a shell inside a shell at odd depth becomes a cavity (inward), at even depth a solid; overlapping shells are left alone |
| `SEPARATE` | the copies of a split vertex are nudged apart by a few micrometres so that parts that touch stop sharing edges when a consumer merges equal vertices (that is what makes the result "watertight" for trimesh, admesh and slicers alike) |
| `CHECK_SELF_INTERSECTIONS` | diagnostic only: counts faces that pierce each other (reported, not repaired) |

Every stage can be switched off, `flags = 0` changes nothing, and the report counts what each stage did.

## Install and build

```sh
pip install "meshfix @ git+https://github.com/alex-mextner/meshfix@v0.1.1"   # builds from source: C++17 compiler + CMake
pip install .                        # the same from a checkout (scikit-build-core is fetched by pip)
# Prebuilt wheels (py3-none, libmeshfix inside, numpy optional) for Linux, macOS and Windows are attached to each
# GitHub release by the `wheels` workflow.

cmake -S . -B build && cmake --build build -j
ctest --test-dir build --output-on-failure
cmake --install build --prefix /usr/local        # libmeshfix.{so,a}, meshfix.h, meshfixConfig.cmake, `meshfix` CLI
```

CMake options: `MESHFIX_BUILD_SHARED`, `MESHFIX_BUILD_STATIC`, `MESHFIX_BUILD_CLI`, `MESHFIX_BUILD_TESTS`.
Use it from CMake with `find_package(meshfix)` (`meshfix::meshfix`, `meshfix::meshfix_static`) or
`add_subdirectory` / `FetchContent`:

```cmake
include(FetchContent)
FetchContent_Declare(meshfix GIT_REPOSITORY https://github.com/alex-mextner/meshfix.git GIT_TAG v0.1.1)
set(MESHFIX_BUILD_CLI OFF) set(MESHFIX_BUILD_TESTS OFF)
FetchContent_MakeAvailable(meshfix)
target_link_libraries(app PRIVATE meshfix::meshfix_static)
```

## C

```c
#include "meshfix.h"

meshfix_mesh *in = NULL, *out = NULL;
meshfix_mesh_create(vertices /* 3*n doubles */, n_vertices, faces /* 3*m uint32 */, n_faces, &in);

meshfix_options opts;  meshfix_options_init(&opts);     /* defaults + struct_size */
opts.max_hole_edges = 500;                               /* leave bigger holes open */
meshfix_report rep;    meshfix_report_init(&rep);

if (meshfix_repair(in, &opts, &out, &rep) == MESHFIX_OK) {
    const double   *v = meshfix_mesh_vertices(out);      /* borrowed until meshfix_mesh_free(out) */
    const uint32_t *f = meshfix_mesh_faces(out);
    printf("watertight %d -> %d, %llu holes filled\n", rep.watertight_before, rep.watertight_after,
           (unsigned long long)rep.holes_filled);
}
meshfix_mesh_free(in);  meshfix_mesh_free(out);
```

The complete program is [`examples/example.c`](examples/example.c) (built and run by CTest). Also in the C API:
`meshfix_analyze` (inspect without repairing), `meshfix_mesh_read` / `meshfix_mesh_write` (.stl binary/ASCII, .obj),
`meshfix_report_to_json`, a progress callback with cancellation (`options.progress`), `meshfix_last_error`.

## Python

```python
import meshfix

vertices, faces, report = meshfix.repair(vertices, faces)            # (N,3) floats, (M,3) indices; lists or numpy
vertices, faces, report = meshfix.repair(vertices, faces, max_hole_edges=500,
                                         flags=int(meshfix.Fix.ALL & ~meshfix.Fix.NESTED_SHELLS))
report = meshfix.repair_file("in.stl", "out.stl")                    # .stl / .obj
report = meshfix.analyze(vertices, faces)                            # no repair
report.watertight_before, report.watertight_after, report.volume_after, report.holes_filled
report.to_dict()                                                     # all fields, plain types
```

`meshfix.repair(vertices, faces, options) -> (vertices, faces, report)` mirrors `meshfix_repair`; `Options`, `Fix`
and `Report` mirror `meshfix_options`, the `MESHFIX_FIX_*` flags and `meshfix_report` field for field. Errors raise
`meshfix.MeshfixError` (`.status` is the `MESHFIX_ERR_*` code). numpy is optional: without it meshes are lists
of tuples. The binding is plain `ctypes` over the C ABI, so one wheel serves every Python version; set
`MESHFIX_LIBRARY=/path/to/libmeshfix.so` to use another build. Runnable: [`examples/example.py`](examples/example.py).

## Command line

```
meshfix in.stl -o out.stl --report json
meshfix in.stl --analyze                      # inspect only
meshfix in.stl -o out.stl --no-nested-shells --max-hole-edges 200
```

Exit status: `0` the result is watertight, `1` it is not, `2` usage or I/O error. `--report json` prints the
report on stdout. `meshfix --help` lists every option.

## The report

`meshfix_report` / `Report`: `watertight_before/after`, `manifold_before/after`, `volume_before/after` (signed;
negative means inside-out), face and vertex counts, and per stage: `vertices_merged`, `degenerate_faces_removed`,
`duplicate_faces_removed`, `t_junctions_fixed`, `faces_flipped`, `non_manifold_edges_before/after`,
`non_manifold_vertices_split`, `boundary_edges_before/after`, `holes_found/filled/skipped`, `hole_faces_added`,
`components_before/after`, `small_components_removed`, `flat_components_removed`, `cavity_shells`,
`vertices_separated`, `self_intersections_remain`/`self_intersecting_pairs`, `elapsed_ms`.

*Watertight* means every edge has exactly two faces and the winding is consistent, judged the way an STL consumer
sees the mesh: vertices with exactly equal coordinates are one vertex. A result that is watertight here is
watertight for trimesh, admesh and slicers. The self-intersection check counts proper piercings only (an edge
through a face's interior, clear of the borders by more than the weld tolerance); it is a diagnostic, not a proof.

## Benchmarks

Single thread, one run, release build (`bench/bench.py`; trimesh is only used as an independent second opinion on
the result). Times: a 16-core Linux server (conda-forge GCC 16, `-O3`); the same runs took about 3x longer on a
loaded laptop (GCC 15).

| Mesh | Faces before -> after | Watertight (meshfix / trimesh) | Volume before -> after | Time |
|---|---|---|---|---|
| Real marketplace STL ("cat phone holder", 20 MB, not redistributable, so not in this repo) | 411,213 -> 411,110 | no -> yes / no -> yes | 78151.5 -> 78151.5 mm^3 | 1.5 s |
| `bench.py --synthetic 7`: 327k-face sphere soup with 820k duplicate noisy vertices, 12 holes, 1,638 flipped and 655 duplicate faces | 328,263 -> 327,656 | no -> yes / no -> yes | 4.154 -> 4.189 (exact 4.1887) | 1.3 s |

Trimesh on the real mesh before: not watertight, 37 open edges, 87 edges with 3-4 faces (parts of the model touch
along edges) and 100 duplicated faces. After: `is_watertight`, `is_winding_consistent`, `is_volume`, volume 78151.494. The repair is
deterministic: the same input gives byte-identical output.

## ABI stability policy

- The public interface is `include/meshfix.h`: `extern "C"`, fixed-width types, opaque handles, no C++ types.
- `MESHFIX_ABI_VERSION` (and `meshfix_abi_version()`) changes only when the existing ABI breaks - never for
  additions. Semantic versioning on the package: patch/minor never break the ABI; a major bump may.
- Structs that cross the boundary (`meshfix_options`, `meshfix_report`) start with `struct_size`. The caller sets
  it to `sizeof` of the header it was compiled against (`meshfix_options_init`, `meshfix_report_init`). The library
  reads/writes only that many bytes: an old binary works with a new library (new fields keep their defaults), a
  new binary with an old library (extra fields are not touched). New fields are only appended.
- Ownership is explicit: handles from `*_create`/`*_read`/`meshfix_repair` are released with `meshfix_mesh_free`;
  vertex/face pointers are borrowed from the handle. The library never frees caller memory and never keeps
  pointers you pass in (`meshfix_mesh_create` copies).
- Errors are status codes (`meshfix_status`) plus `meshfix_last_error()` (thread-local). No exception crosses the C
  boundary. The library keeps no global state, so concurrent calls on different meshes are safe.

## Licence and provenance

MIT, see [LICENSE](LICENSE).

This library grew out of the "Fix model" mesh repair in the author's
[Snapmaker Orca fork](https://github.com/alex-mextner/SnapOrca) (CGAL-based, in an AGPL-3.0 codebase, which itself
traces back to OrcaSlicer / PrusaSlicer). meshfix is a **clean re-implementation** of the behaviour: it contains
no code from libslic3r, admesh, CGAL (GPL-3.0+), PrusaSlicer or OrcaSlicer, and links nothing but the C++ standard
library. The few algorithmic ideas that were carried over (grid-based vertex welding, splitting pinched hole
boundaries at repeated points, shell nesting depth by the longest containment chain) come from code the author
wrote himself for that fork and re-licenses here as the copyright holder; they are re-implemented on a different
data structure, not copied. Because of that, and because of its own tests, it can be used from the AGPL Orca fork
(AGPL code may use MIT code) and from closed or permissive projects alike.

## Limits (v0.1)

- Triangles only; STL (binary/ASCII) and OBJ I/O. 3MF/PLY: read them with your own loader and call `meshfix_repair`.
- Holes are filled to close the mesh, not to be pretty: a hole is triangulated from its own boundary (no fairing,
  no curvature continuation). Meshes with huge missing regions need a modeller.
- Self-intersections and overlapping shells are reported, not resolved (no boolean union). Slicers handle them.
- Little-endian hosts only for STL I/O.
