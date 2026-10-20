"""Python mirror of tests/test_meshfix.cpp. Every defect test also runs with the repair off (Fix.NONE)
and checks the defect is still there."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

import meshfix
from meshfix import Fix
from meshgen import concat, cube, drop_faces, flip_all, sphere, volume

ALL = Fix.ALL | Fix.CHECK_SELF_INTERSECTIONS
OFF = Fix.NONE


def run(mesh, flags=ALL, **kw):
    return meshfix.repair(mesh[0], mesh[1], meshfix.Options(flags=int(flags), **kw))


def test_version_and_abi():
    assert meshfix.version() == meshfix.__version__ == "0.1.0"
    assert meshfix.abi_version() == 1


def test_clean_cube_is_untouched():
    v, f, r = run(cube())
    assert r.watertight_before and r.watertight_after and len(f) == 12 and len(v) == 8
    assert r.volume_after == pytest.approx(1.0)
    assert r.self_intersections_remain is False
    assert r.faces_flipped == r.holes_found == r.duplicate_faces_removed == 0


def test_holes_are_filled_and_teeth():
    open_cube = drop_faces(cube(), [2, 3])
    v, f, r = run(open_cube)
    assert not r.watertight_before and r.boundary_edges_before == 4
    assert r.watertight_after and r.boundary_edges_after == 0
    assert (r.holes_found, r.holes_filled, r.hole_faces_added) == (1, 1, 2)
    assert r.volume_after == pytest.approx(1.0)
    _, f_off, r_off = run(open_cube, OFF)
    assert not r_off.watertight_after and r_off.boundary_edges_after == 4 and len(f_off) == 10

    ball = sphere(1.0, 2)
    holed = drop_faces(ball, range(7))
    _, _, rs = run(holed)
    assert rs.watertight_after and 0.9 * volume(ball) < rs.volume_after < 1.1 * volume(ball)
    assert not run(holed, OFF)[2].watertight_after
    assert run(open_cube, max_hole_edges=3)[2].holes_skipped == 1


def test_flipped_faces():
    v, f = sphere(1.0, 2)
    full = volume((v, f))
    f = f.copy()
    for i in (3, 17, 40, 41, 120, 200, 311):
        f[i] = f[i][::-1]
    _, _, r = run((v, f))
    assert not r.watertight_before and r.watertight_after and r.faces_flipped == 7
    assert r.volume_after == pytest.approx(full, rel=1e-9)
    r_off = run((v, f), OFF)[2]
    assert not r_off.watertight_after and r_off.faces_flipped == 0

    inverted = flip_all(cube())
    r = run(inverted)[2]
    assert r.volume_before == pytest.approx(-1.0) and r.volume_after == pytest.approx(1.0)
    assert run(inverted, OFF)[2].volume_after == pytest.approx(-1.0)


def test_duplicate_vertices_with_noise():
    v, f = sphere(1.0, 2)
    rng = np.random.default_rng(7)
    soup_v = v[f].reshape(-1, 3) + rng.uniform(-1e-7, 1e-7, (len(f) * 3, 3))
    soup_f = np.arange(len(f) * 3, dtype=np.uint32).reshape(-1, 3)
    out_v, out_f, r = run((soup_v, soup_f))
    assert not r.watertight_before and r.watertight_after
    assert len(out_v) == len(v) and r.vertices_merged == len(soup_v) - len(v)
    assert r.volume_after == pytest.approx(volume((v, f)), abs=0.01)
    off_v, _, r_off = run((soup_v, soup_f), OFF)
    assert not r_off.watertight_after and len(off_v) == len(soup_v)


def test_duplicate_and_degenerate_faces():
    v, f = cube()
    c = (v, np.vstack([f, [[0, 3, 2], [4, 5, 6], [1, 2, 6]]]).astype(np.uint32))
    out_v, out_f, r = run(c)
    assert not r.manifold_before and r.duplicate_faces_removed == 3 and len(out_f) == 12 and r.watertight_after
    assert len(run(c, OFF)[1]) == 15

    d_v = np.vstack([v, [[0.5, 0, 0]]])
    d_f = np.vstack([f, [[0, 0, 1], [0, 1, 8]]]).astype(np.uint32)
    _, _, rd = run((d_v, d_f))
    assert rd.degenerate_faces_removed >= 1 and rd.watertight_after
    assert len(run((d_v, d_f), OFF)[1]) == 14

    bad_v = np.vstack([v, [[np.nan, 0, 0]]])
    bad_f = np.vstack([f, [[0, 1, 99], [0, 1, 8]]]).astype(np.uint32)
    _, _, rb = run((bad_v, bad_f))
    assert rb.invalid_faces_removed == 2 and rb.watertight_after


def test_non_manifold_edges():
    two = concat(cube(), cube(origin=(1, 1, 0)))
    _, _, r = run(two)
    assert r.non_manifold_edges_before == 1 and not r.manifold_before and not r.watertight_before
    assert r.non_manifold_edges_after == 0 and r.watertight_after and r.manifold_after
    assert (r.components_before, r.components_after) == (1, 2)
    assert r.volume_after == pytest.approx(2.0, abs=1e-3)
    assert not run(two, OFF)[2].watertight_after
    assert run(two, Fix.WELD)[2].non_manifold_edges_after == 1

    v, f = cube()
    finned = (np.vstack([v, [[0.5, -1, -1]]]), np.vstack([f, [[0, 1, 8]]]).astype(np.uint32))
    r = run(finned)[2]
    assert r.non_manifold_edges_before == 1 and r.watertight_after and r.non_manifold_edges_after == 0
    assert r.volume_after == pytest.approx(1.0)
    assert run(finned, OFF)[2].non_manifold_edges_after == 1

    bow = concat(cube(), cube(origin=(1, 1, 1)))
    r = run(bow)[2]
    assert not r.manifold_before and r.manifold_after and r.watertight_after


def test_t_junctions():
    v, f = cube()
    f = np.delete(f, [2, 3], axis=0)
    v = np.vstack([v, [[0.5, 0, 1]]])
    f = np.vstack([f, [[4, 8, 7], [8, 5, 7], [5, 6, 7]]]).astype(np.uint32)
    _, _, r = run((v, f))
    assert not r.watertight_before
    assert r.t_junctions_fixed == 1 and r.watertight_after and r.holes_found == 0
    assert r.volume_after == pytest.approx(1.0)
    r_off = run((v, f), OFF)[2]
    assert not r_off.watertight_after and r_off.t_junctions_fixed == 0
    assert not run((v, f), ALL & ~Fix.T_JUNCTIONS & ~Fix.HOLES)[2].watertight_after


def test_islands():
    v, f = sphere(5.0, 2)
    pieces = (v, f)
    for i in range(3):
        o = 20 + 3 * i
        tv = np.array([[o, 0, 0], [o + .1, 0, 0], [o, .1, 0], [o, 0, .1]], float)
        tf = np.array([[0, 2, 1], [0, 1, 3], [1, 2, 3], [2, 0, 3]], np.uint32)
        pieces = concat(pieces, (tv, tf))
    pieces = concat(pieces, (np.array([[40, 0, 0], [41, 0, 0], [40, 1, 0]], float), np.array([[0, 1, 2]], np.uint32)))
    _, out_f, r = run(pieces)
    assert r.components_before == 5 and r.components_after == 1 and r.small_components_removed == 4
    assert len(out_f) == 320 and r.watertight_after
    off = run(pieces, OFF)
    assert off[2].components_after == 5 and len(off[1]) == 333
    assert run(pieces, min_component_faces=1)[2].small_components_removed == 0


def test_nested_shells():
    outer = cube(4)
    solid_in_solid = concat(outer, cube(1, (1.5, 1.5, 1.5)))
    r = run(solid_in_solid)[2]
    assert r.cavity_shells == 1 and r.faces_flipped == 12 and r.volume_after == pytest.approx(63.0)
    assert run(solid_in_solid, OFF)[2].volume_after == pytest.approx(65.0)
    assert run(solid_in_solid, ALL & ~Fix.NESTED_SHELLS)[2].volume_after == pytest.approx(65.0)
    cavity = concat(outer, flip_all(cube(2, (1, 1, 1))))
    assert run(cavity)[2].volume_after == pytest.approx(56.0)
    assert run(concat(cavity, cube(0.5, (1.75, 1.75, 1.75))))[2].volume_after == pytest.approx(56.125)
    overlap = run(concat(cube(), cube(1, (0.5, 0.4, 0.3))))[2]
    assert overlap.cavity_shells == 0 and overlap.self_intersections_remain is True


def test_self_intersection_check():
    assert run(sphere(1, 2))[2].self_intersections_remain is False
    assert run(sphere(1, 2), Fix.ALL)[2].self_intersections_remain is None
    r = run(concat(sphere(1, 2), sphere(1, 2, (0.5, 0.3, 0.2))))[2]
    assert r.self_intersections_remain is True and r.self_intersecting_pairs > 0
    assert run(concat(cube(), cube(origin=(1, 0, 0))))[2].self_intersections_remain is False


def test_determinism():
    m = drop_faces(sphere(2.0, 3), [5, 99, 100, 101, 400])
    m = concat(m, cube(1, (5, 5, 5)))
    a, b = run(m), run(m)
    assert np.array_equal(a[0], b[0]) and np.array_equal(a[1], b[1])


def test_api_shape():
    v, f = cube()
    # plain lists work, results are numpy arrays
    out_v, out_f, r = meshfix.repair(v.tolist(), f.tolist())
    assert out_v.shape == (8, 3) and out_f.shape == (12, 3) and out_f.dtype == np.uint32
    d = r.to_dict()
    for key in ("watertight_before", "watertight_after", "volume_before", "volume_after", "faces_before",
                "faces_after", "holes_filled"):
        assert key in d
    assert d["faces_before"] == 12 and d["faces_after"] == 12
    # keyword overrides and unknown options
    assert meshfix.repair(v, f, flags=int(Fix.NONE))[2].elapsed_ms >= 0
    with pytest.raises(TypeError):
        meshfix.repair(v, f, bogus=1)
    with pytest.raises(ValueError):
        meshfix.repair(v, f[:, :2])
    with pytest.raises(ValueError):
        meshfix.repair(v, f.astype(float))
    with pytest.raises(meshfix.MeshfixError) as e:
        meshfix.repair(v, np.zeros((0, 3), np.uint32))
    assert e.value.status == 3
    assert meshfix.analyze(*drop_faces((v, f), [2, 3])).boundary_edges_before == 4


def test_progress_and_cancel():
    stages = []

    def record(stage, fraction):
        stages.append((stage, fraction))
        return False

    meshfix.repair(*cube(), progress=record)
    names = [s for s, _ in stages]
    assert names[0] == "sanitize" and names[-1] == "done" and "holes" in names
    assert [f for _, f in stages] == sorted(f for _, f in stages)
    with pytest.raises(meshfix.MeshfixError) as e:
        meshfix.repair(*cube(), progress=lambda stage, fraction: stage == "holes")
    assert e.value.status == 4
    with pytest.raises(meshfix.MeshfixError):  # an exception in the callback cancels instead of crashing
        meshfix.repair(*cube(), progress=lambda stage, fraction: 1 / 0)


def _write_binary_stl(path: Path, v, f):
    rec = np.zeros(len(f), dtype=[("n", "<f4", 3), ("t", "<f4", (3, 3)), ("a", "<u2")])
    rec["t"] = v[f].astype("<f4")
    with open(path, "wb") as fh:
        fh.write(b"\0" * 80 + np.uint32(len(f)).tobytes())
        fh.write(rec.tobytes())


def test_repair_file_roundtrip(tmp_path):
    v, f = drop_faces(sphere(1.0, 2), [1, 2, 3])
    src, dst = tmp_path / "in.stl", tmp_path / "out.stl"
    _write_binary_stl(src, v, f)
    r = meshfix.repair_file(src, dst)
    assert not r.watertight_before and r.watertight_after and dst.stat().st_size == 84 + 50 * r.output_faces
    again = meshfix.repair_file(dst)
    assert again.watertight_before and again.holes_found == 0
    with pytest.raises(meshfix.MeshfixError) as e:
        meshfix.repair_file(tmp_path / "missing.stl")
    assert e.value.status == 5
    meshfix.repair_file(src, tmp_path / "out.obj")
    assert (tmp_path / "out.obj").read_text().startswith("v ")


def _cli():
    exe = os.environ.get("MESHFIX_CLI") or shutil.which("meshfix")
    here = Path(__file__).resolve().parents[2] / "build" / "meshfix"
    if not exe and here.exists():
        exe = str(here)
    if not exe:
        pytest.skip("meshfix CLI not built")
    return exe


def test_cli_json_report(tmp_path):
    v, f = drop_faces(sphere(1.0, 2), [1, 2, 3])
    src, dst = tmp_path / "in.stl", tmp_path / "out.stl"
    _write_binary_stl(src, v, f)
    p = subprocess.run([_cli(), str(src), "-o", str(dst), "--report", "json", "--no-self-intersection-check"],
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    report = json.loads(p.stdout)
    assert report["watertight_before"] is False and report["watertight_after"] is True
    assert report["holes_filled"] == 1 and report["self_intersections_remain"] is None
    assert dst.exists()
    off = subprocess.run([_cli(), str(src), "--only", "weld", "--report", "json"], capture_output=True, text=True)
    assert off.returncode == 1 and json.loads(off.stdout)["watertight_after"] is False
    assert subprocess.run([_cli(), str(tmp_path / "nope.stl")], capture_output=True).returncode == 2
    analyzed = subprocess.run([_cli(), str(src), "--analyze", "--report", "json"], capture_output=True, text=True)
    assert analyzed.returncode == 1
    both = subprocess.run([_cli(), str(src), "--analyze", "-o", str(tmp_path / "x.stl")], capture_output=True)
    assert both.returncode == 2
