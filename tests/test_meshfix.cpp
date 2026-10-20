// CTest suite: generated defective meshes through the C ABI. Every defect test also runs with the repair
// disabled (flags = 0) and checks the defect is still there, so the tests cannot pass on an untouched mesh.
// SPDX-License-Identifier: MIT
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include <string>
#include <vector>

#include "meshfix.h"

namespace {

constexpr double kPi = 3.14159265358979323846; // M_PI is not in MSVC's <cmath> by default

int g_failures = 0;
int g_checks = 0;

#define CHECK(cond)                                                                        \
    do {                                                                                   \
        ++g_checks;                                                                        \
        if (!(cond)) {                                                                     \
            ++g_failures;                                                                  \
            std::fprintf(stderr, "  FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);         \
        }                                                                                  \
    } while (0)

#define CHECK_NEAR(a, b, tol)                                                                              \
    do {                                                                                                   \
        ++g_checks;                                                                                        \
        if (!(std::fabs((a) - (b)) <= (tol))) {                                                            \
            ++g_failures;                                                                                  \
            std::fprintf(stderr, "  FAIL %s:%d: %s = %.9g, expected %.9g +- %g\n", __FILE__, __LINE__, #a, \
                         double(a), double(b), double(tol));                                               \
        }                                                                                                  \
    } while (0)

struct M {
    std::vector<double> v;
    std::vector<uint32_t> f;
    size_t nv() const { return v.size() / 3; }
    size_t nf() const { return f.size() / 3; }
    uint32_t add_vertex(double x, double y, double z) {
        v.insert(v.end(), {x, y, z});
        return uint32_t(nv() - 1);
    }
    void add_face(uint32_t a, uint32_t b, uint32_t c) { f.insert(f.end(), {a, b, c}); }
};

M cube(double s = 1, double ox = 0, double oy = 0, double oz = 0) {
    M m;
    const double c[8][3] = {{0, 0, 0}, {1, 0, 0}, {1, 1, 0}, {0, 1, 0}, {0, 0, 1}, {1, 0, 1}, {1, 1, 1}, {0, 1, 1}};
    for (const auto &p : c)
        m.add_vertex(ox + s * p[0], oy + s * p[1], oz + s * p[2]);
    const uint32_t faces[12][3] = {{0, 3, 2}, {0, 2, 1}, {4, 5, 6}, {4, 6, 7}, {0, 1, 5}, {0, 5, 4},
                                   {3, 7, 6}, {3, 6, 2}, {0, 4, 7}, {0, 7, 3}, {1, 2, 6}, {1, 6, 5}};
    for (const auto &t : faces)
        m.add_face(t[0], t[1], t[2]);
    return m;
}

// Icosphere of radius r around (ox, oy, oz), `levels` subdivisions: 20 * 4^levels faces.
M sphere(double r, int levels, double ox = 0, double oy = 0, double oz = 0) {
    M m;
    const double t = (1.0 + std::sqrt(5.0)) / 2.0;
    const double base[12][3] = {{-1, t, 0}, {1, t, 0}, {-1, -t, 0}, {1, -t, 0}, {0, -1, t}, {0, 1, t},
                                {0, -1, -t}, {0, 1, -t}, {t, 0, -1}, {t, 0, 1}, {-t, 0, -1}, {-t, 0, 1}};
    for (const auto &p : base) {
        const double l = std::sqrt(p[0] * p[0] + p[1] * p[1] + p[2] * p[2]);
        m.add_vertex(p[0] / l, p[1] / l, p[2] / l);
    }
    std::vector<uint32_t> faces = {0, 11, 5, 0, 5, 1, 0, 1, 7, 0, 7, 10, 0, 10, 11, 1, 5, 9, 5, 11, 4, 11, 10, 2, 10, 7, 6, 7, 1, 8,
                                   3, 9, 4, 3, 4, 2, 3, 2, 6, 3, 6, 8, 3, 8, 9, 4, 9, 5, 2, 4, 11, 6, 2, 10, 8, 6, 7, 9, 8, 1};
    for (int l = 0; l < levels; ++l) {
        std::map<std::pair<uint32_t, uint32_t>, uint32_t> mid;
        const auto midpoint = [&](uint32_t a, uint32_t b) {
            const auto key = std::make_pair(std::min(a, b), std::max(a, b));
            const auto it = mid.find(key);
            if (it != mid.end())
                return it->second;
            double p[3];
            for (int k = 0; k < 3; ++k)
                p[k] = (m.v[3 * a + k] + m.v[3 * b + k]) / 2;
            const double len = std::sqrt(p[0] * p[0] + p[1] * p[1] + p[2] * p[2]);
            return mid[key] = m.add_vertex(p[0] / len, p[1] / len, p[2] / len);
        };
        std::vector<uint32_t> next;
        for (size_t i = 0; i < faces.size(); i += 3) {
            const uint32_t a = faces[i], b = faces[i + 1], c = faces[i + 2];
            const uint32_t ab = midpoint(a, b), bc = midpoint(b, c), ca = midpoint(c, a);
            next.insert(next.end(), {a, ab, ca, b, bc, ab, c, ca, bc, ab, bc, ca});
        }
        faces = next;
    }
    m.f = faces;
    for (size_t i = 0; i < m.nv(); ++i) {
        m.v[3 * i] = ox + r * m.v[3 * i];
        m.v[3 * i + 1] = oy + r * m.v[3 * i + 1];
        m.v[3 * i + 2] = oz + r * m.v[3 * i + 2];
    }
    return m;
}

// Latitude/longitude sphere: the rings are planar, like the sphere of the Orca fork's tests.
M uv_sphere(double r, int rings, int segments) {
    M m;
    const uint32_t north = m.add_vertex(0, 0, r);
    for (int i = 1; i < rings; ++i) {
        const double phi = kPi * i / rings;
        for (int j = 0; j < segments; ++j) {
            const double th = 2 * kPi * j / segments;
            m.add_vertex(r * std::sin(phi) * std::cos(th), r * std::sin(phi) * std::sin(th), r * std::cos(phi));
        }
    }
    const uint32_t south = m.add_vertex(0, 0, -r);
    const auto at = [&](int ring, int j) { return uint32_t(1 + (ring - 1) * segments + (j % segments)); };
    for (int j = 0; j < segments; ++j)
        m.add_face(north, at(1, j), at(1, j + 1));
    for (int i = 1; i + 1 < rings; ++i)
        for (int j = 0; j < segments; ++j) {
            m.add_face(at(i, j), at(i + 1, j), at(i + 1, j + 1));
            m.add_face(at(i, j), at(i + 1, j + 1), at(i, j + 1));
        }
    for (int j = 0; j < segments; ++j)
        m.add_face(south, at(rings - 1, j + 1), at(rings - 1, j));
    return m;
}

M concat(const M &a, const M &b) {
    M m = a;
    const uint32_t off = uint32_t(a.nv());
    m.v.insert(m.v.end(), b.v.begin(), b.v.end());
    for (uint32_t x : b.f)
        m.f.push_back(x + off);
    return m;
}

M flip_all(M m) {
    for (size_t i = 0; i < m.nf(); ++i)
        std::swap(m.f[3 * i + 1], m.f[3 * i + 2]);
    return m;
}

M drop_faces(const M &m, const std::vector<size_t> &faces) {
    M out;
    out.v = m.v;
    for (size_t i = 0; i < m.nf(); ++i) {
        bool drop = false;
        for (size_t d : faces)
            drop = drop || d == i;
        if (!drop)
            out.add_face(m.f[3 * i], m.f[3 * i + 1], m.f[3 * i + 2]);
    }
    return out;
}

double volume(const M &m) {
    double vol = 0;
    for (size_t i = 0; i < m.nf(); ++i) {
        const double *a = &m.v[3 * m.f[3 * i]], *b = &m.v[3 * m.f[3 * i + 1]], *c = &m.v[3 * m.f[3 * i + 2]];
        vol += a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0]) + a[2] * (b[0] * c[1] - b[1] * c[0]);
    }
    return vol / 6;
}

struct Result {
    M mesh;
    meshfix_report r;
    meshfix_status status;
};

Result run(const M &in, uint32_t flags, double tol = -1.0, void (*tweak)(meshfix_options *) = nullptr) {
    Result res;
    meshfix_report_init(&res.r);
    meshfix_mesh *src = nullptr, *out = nullptr;
    meshfix_status st = meshfix_mesh_create(in.v.data(), in.nv(), in.f.data(), in.nf(), &src);
    CHECK(st == MESHFIX_OK);
    meshfix_options o;
    meshfix_options_init(&o);
    o.flags = flags;
    o.weld_tolerance = tol;
    if (tweak)
        tweak(&o);
    res.status = meshfix_repair(src, &o, &out, &res.r);
    if (out) {
        const double *v = meshfix_mesh_vertices(out);
        const uint32_t *f = meshfix_mesh_faces(out);
        if (v) // the arrays are NULL for an empty mesh
            res.mesh.v.assign(v, v + 3 * meshfix_mesh_vertex_count(out));
        if (f)
            res.mesh.f.assign(f, f + 3 * meshfix_mesh_face_count(out));
    }
    meshfix_mesh_free(src);
    meshfix_mesh_free(out);
    return res;
}

constexpr uint32_t kAll = MESHFIX_FIX_ALL | MESHFIX_CHECK_SELF_INTERSECTIONS;
constexpr uint32_t kOff = 0;

// ------------------------------------------------------------------------------------------------

void test_clean_cube_is_untouched() {
    std::puts("clean cube");
    const Result r = run(cube(), kAll);
    CHECK(r.status == MESHFIX_OK);
    CHECK(r.r.watertight_before == 1 && r.r.watertight_after == 1);
    CHECK(r.mesh.nf() == 12 && r.mesh.nv() == 8);
    CHECK_NEAR(r.r.volume_after, 1.0, 1e-12);
    CHECK(r.r.self_intersections_remain == 0);
    CHECK(r.r.holes_found == 0 && r.r.faces_flipped == 0 && r.r.duplicate_faces_removed == 0);
}

void test_holes() {
    std::puts("holes");
    // A cube missing its top quad.
    const M open_cube = drop_faces(cube(), {2, 3});
    const Result fixed = run(open_cube, kAll);
    CHECK(fixed.r.watertight_before == 0 && fixed.r.boundary_edges_before == 4);
    CHECK(fixed.r.watertight_after == 1 && fixed.r.boundary_edges_after == 0);
    CHECK(fixed.r.holes_found == 1 && fixed.r.holes_filled == 1 && fixed.r.hole_faces_added == 2);
    CHECK_NEAR(fixed.r.volume_after, 1.0, 1e-12);
    const Result off = run(open_cube, kOff);
    CHECK(off.r.watertight_after == 0 && off.r.boundary_edges_after == 4 && off.mesh.nf() == 10);

    // A sphere with a fan of faces cut out: the hole follows a curved boundary.
    const M ball = sphere(1.0, 2);
    const double full = volume(ball);
    const M holed = drop_faces(ball, {0, 1, 2, 3, 4, 5, 6});
    const Result rs = run(holed, kAll);
    CHECK(rs.r.watertight_before == 0 && rs.r.watertight_after == 1);
    CHECK(rs.r.holes_filled >= 1);
    CHECK(rs.r.volume_after > 0.9 * full && rs.r.volume_after < 1.1 * full);
    CHECK(run(holed, kOff).r.watertight_after == 0);

    // max_hole_edges leaves big holes alone.
    const Result limited = run(open_cube, kAll, -1.0, [](meshfix_options *o) { o->max_hole_edges = 3; });
    CHECK(limited.r.holes_skipped == 1 && limited.r.watertight_after == 0);
}

void test_flipped_faces() {
    std::puts("flipped faces");
    M ball = sphere(1.0, 2);
    const double full = volume(ball);
    for (size_t i : {3u, 17u, 40u, 41u, 120u, 200u, 311u})
        std::swap(ball.f[3 * i + 1], ball.f[3 * i + 2]);
    const Result fixed = run(ball, kAll);
    CHECK(fixed.r.watertight_before == 0);
    CHECK(fixed.r.watertight_after == 1 && fixed.r.faces_flipped == 7);
    CHECK_NEAR(fixed.r.volume_after, full, 1e-9);
    const Result off = run(ball, kOff);
    CHECK(off.r.watertight_after == 0 && off.r.faces_flipped == 0);

    // A whole inside-out mesh: negative volume before, positive after.
    const M inverted = flip_all(cube());
    const Result ri = run(inverted, kAll);
    CHECK_NEAR(ri.r.volume_before, -1.0, 1e-12);
    CHECK_NEAR(ri.r.volume_after, 1.0, 1e-12);
    CHECK(ri.r.faces_flipped == 12 && ri.r.watertight_after == 1);
    CHECK_NEAR(run(inverted, kOff).r.volume_after, -1.0, 1e-12);
}

void test_duplicate_vertices() {
    std::puts("duplicate and near-duplicate vertices");
    // Every face carries its own copy of its vertices (an STL soup), with sub-tolerance noise.
    const M ball = sphere(1.0, 2);
    M soup;
    unsigned seed = 7;
    for (size_t i = 0; i < ball.nf(); ++i) {
        uint32_t ids[3];
        for (int k = 0; k < 3; ++k) {
            const double *p = &ball.v[3 * ball.f[3 * i + k]];
            seed = seed * 1664525u + 1013904223u;
            const double noise = ((seed >> 8) % 1000) / 1000.0 * 2e-7 - 1e-7;
            ids[k] = soup.add_vertex(p[0] + noise, p[1] - noise, p[2] + noise);
        }
        soup.add_face(ids[0], ids[1], ids[2]);
    }
    const Result fixed = run(soup, kAll);
    CHECK(fixed.r.watertight_before == 0);
    CHECK(fixed.r.watertight_after == 1);
    CHECK(fixed.mesh.nv() == ball.nv());
    CHECK(fixed.r.vertices_merged == soup.nv() - ball.nv());
    CHECK_NEAR(fixed.r.volume_after, volume(ball), 0.01);
    const Result off = run(soup, kOff);
    CHECK(off.r.watertight_after == 0 && off.mesh.nv() == soup.nv());

    // Exactly equal copies need no tolerance.
    M exact = soup;
    for (size_t i = 0; i < exact.nf(); ++i)
        for (int k = 0; k < 3; ++k)
            for (int c = 0; c < 3; ++c)
                exact.v[3 * exact.f[3 * i + k] + c] = ball.v[3 * ball.f[3 * i + k] + c];
    const Result re = run(exact, kAll, 0.0);
    CHECK(re.r.watertight_before == 1 && re.r.watertight_after == 1 && re.mesh.nv() == ball.nv());
}

void test_duplicate_and_degenerate_faces() {
    std::puts("duplicate and degenerate faces");
    M c = cube();
    c.add_face(0, 3, 2); // the bottom triangle twice
    c.add_face(4, 5, 6);
    c.add_face(1, 2, 6);
    const Result fixed = run(c, kAll);
    CHECK(fixed.r.manifold_before == 0 && fixed.r.non_manifold_edges_before > 0);
    CHECK(fixed.r.duplicate_faces_removed == 3 && fixed.mesh.nf() == 12 && fixed.r.watertight_after == 1);
    const Result off = run(c, kOff);
    CHECK(off.mesh.nf() == 15 && off.r.non_manifold_edges_after > 0);

    M d = cube();
    d.add_face(0, 0, 1);             // repeated index
    d.add_face(0, 1, d.add_vertex(0.5, 0, 0)); // a needle: the third corner lies on the first edge
    const Result rd = run(d, kAll);
    CHECK(rd.r.degenerate_faces_removed >= 1);
    CHECK(rd.r.watertight_after == 1 && rd.mesh.nf() >= 12);
    CHECK(run(d, kOff).mesh.nf() == 14);

    // Faces that point at missing vertices or non-finite coordinates are dropped, not crashed on.
    M bad = cube();
    bad.add_face(0, 1, 99);
    bad.add_vertex(NAN, 0, 0);
    bad.add_face(0, 1, uint32_t(bad.nv() - 1));
    const Result rb = run(bad, kAll);
    CHECK(rb.status == MESHFIX_OK && rb.r.invalid_faces_removed == 2 && rb.r.watertight_after == 1);
}

void test_back_to_back_faces_cancel() {
    std::puts("back-to-back faces");
    M c = cube();
    c.add_face(0, 2, 3); // the bottom triangle (0,3,2) again, reversed: a zero-thickness sheet
    const Result fixed = run(c, kAll);
    // The pair cancels, which leaves the cube without that triangle; the hole filler puts one back.
    CHECK(fixed.r.duplicate_faces_removed == 2 && fixed.r.holes_filled == 1);
    CHECK(fixed.r.watertight_after == 1 && fixed.mesh.nf() == 12);
    CHECK_NEAR(fixed.r.volume_after, 1.0, 1e-12);
    CHECK(run(c, kOff).r.manifold_after == 0);
}

void test_non_manifold_edges() {
    std::puts("non-manifold edges");
    // Two cubes that touch along the edge x = 1, y = 1.
    const M two = concat(cube(), cube(1, 1, 1, 0));
    const Result fixed = run(two, kAll);
    CHECK(fixed.r.non_manifold_edges_before == 1 && fixed.r.manifold_before == 0 && fixed.r.watertight_before == 0);
    CHECK(fixed.r.non_manifold_edges_after == 0 && fixed.r.watertight_after == 1 && fixed.r.manifold_after == 1);
    CHECK(fixed.r.components_before == 1 && fixed.r.components_after == 2);
    CHECK_NEAR(fixed.r.volume_after, 2.0, 1e-3); // the touching copies were nudged inward
    CHECK(fixed.r.non_manifold_vertices_split > 0);
    const Result off = run(two, kOff);
    CHECK(off.r.watertight_after == 0);
    const Result weld_only = run(two, MESHFIX_FIX_WELD);
    CHECK(weld_only.r.non_manifold_edges_after == 1 && weld_only.r.watertight_after == 0);

    // A fin: one extra triangle on a cube edge.
    M finned = cube();
    const uint32_t tip = finned.add_vertex(0.5, -1.0, -1.0);
    finned.add_face(0, 1, tip);
    const Result rf = run(finned, kAll);
    CHECK(rf.r.non_manifold_edges_before == 1);
    CHECK(rf.r.watertight_after == 1 && rf.r.non_manifold_edges_after == 0);
    CHECK_NEAR(rf.r.volume_after, 1.0, 1e-12);
    CHECK(rf.r.small_components_removed + rf.r.flat_components_removed >= 1);
    CHECK(run(finned, kOff).r.non_manifold_edges_after == 1);

    // Two cubes that share only a corner (a bowtie vertex).
    const M bow = concat(cube(), cube(1, 1, 1, 1));
    const Result rb = run(bow, kAll);
    CHECK(rb.r.manifold_before == 0 && rb.r.manifold_after == 1 && rb.r.watertight_after == 1);
    CHECK(run(bow, kOff).r.manifold_after == 1 ? false : true);
}

void test_t_junctions() {
    std::puts("T-junctions");
    // The top of a cube is split with an extra vertex on its front edge that the front wall does not know.
    M c = cube();
    c.f.resize(3 * 12);
    c.f.erase(c.f.begin() + 3 * 2, c.f.begin() + 3 * 4); // drop the top quad
    const uint32_t m = c.add_vertex(0.5, 0, 1);
    c.add_face(4, m, 7);
    c.add_face(m, 5, 7);
    c.add_face(5, 6, 7);
    const Result fixed = run(c, kAll);
    CHECK(fixed.r.watertight_before == 0);
    CHECK(fixed.r.t_junctions_fixed == 1 && fixed.r.watertight_after == 1 && fixed.r.holes_found == 0);
    CHECK_NEAR(fixed.r.volume_after, 1.0, 1e-12);
    const Result off = run(c, kOff);
    CHECK(off.r.watertight_after == 0 && off.r.t_junctions_fixed == 0);
    // Without the stitching the hole filler cannot close it, the cracks stay.
    const Result no_stitch = run(c, kAll & ~uint32_t(MESHFIX_FIX_T_JUNCTIONS) & ~uint32_t(MESHFIX_FIX_HOLES));
    CHECK(no_stitch.r.watertight_after == 0);
}

void test_islands_and_flat_shells() {
    std::puts("islands");
    M m = sphere(5.0, 2);
    for (int i = 0; i < 3; ++i) { // three tiny tetrahedra
        const double o = 20 + 3 * i;
        const uint32_t a = m.add_vertex(o, 0, 0), b = m.add_vertex(o + 0.1, 0, 0), c = m.add_vertex(o, 0.1, 0), d = m.add_vertex(o, 0, 0.1);
        m.add_face(a, c, b);
        m.add_face(a, b, d);
        m.add_face(b, c, d);
        m.add_face(c, a, d);
    }
    const uint32_t a = m.add_vertex(40, 0, 0), b = m.add_vertex(41, 0, 0), c = m.add_vertex(40, 1, 0);
    m.add_face(a, b, c); // a lone triangle
    const Result fixed = run(m, kAll);
    CHECK(fixed.r.components_before == 5);
    CHECK(fixed.r.components_after == 1 && fixed.r.small_components_removed == 4);
    CHECK(fixed.mesh.nf() == 320 && fixed.r.watertight_after == 1);
    const Result off = run(m, kOff);
    CHECK(off.r.components_after == 5 && off.mesh.nf() == 320 + 12 + 1);
    // The threshold is an option.
    const Result keep = run(m, kAll, -1.0, [](meshfix_options *o) { o->min_component_faces = 1; });
    CHECK(keep.r.small_components_removed == 0 && keep.r.components_after >= 4);
}

void test_nested_shells() {
    std::puts("nested shells");
    const M outer = cube(4);
    const M inner_out = cube(1, 1.5, 1.5, 1.5);
    const M solid_in_solid = concat(outer, inner_out);
    const Result fixed = run(solid_in_solid, kAll);
    CHECK(fixed.r.cavity_shells == 1 && fixed.r.faces_flipped == 12);
    CHECK_NEAR(fixed.r.volume_after, 64.0 - 1.0, 1e-9);
    CHECK_NEAR(run(solid_in_solid, kOff).r.volume_after, 65.0, 1e-9);
    const Result no_nest = run(solid_in_solid, kAll & ~uint32_t(MESHFIX_FIX_NESTED_SHELLS));
    CHECK(no_nest.r.cavity_shells == 0 && std::fabs(no_nest.r.volume_after - 65.0) < 1e-9);
    // A cavity that is already inside-out stays one; a solid inside the cavity is a solid again.
    const M cavity = concat(outer, flip_all(cube(2, 1, 1, 1)));
    const Result rc = run(cavity, kAll);
    CHECK_NEAR(rc.r.volume_after, 64.0 - 8.0, 1e-9);
    const Result island = run(concat(cavity, cube(0.5, 1.75, 1.75, 1.75)), kAll);
    CHECK_NEAR(island.r.volume_after, 64.0 - 8.0 + 0.125, 1e-9);
    // Overlapping, not nested, shells are left alone.
    const Result overlap = run(concat(cube(), cube(1, 0.5, 0.4, 0.3)), kAll);
    CHECK(overlap.r.cavity_shells == 0 && overlap.r.self_intersections_remain == 1);
}

void test_self_intersection_check() {
    std::puts("self-intersection check");
    CHECK(run(sphere(1, 2), kAll).r.self_intersections_remain == 0);
    CHECK(run(sphere(1, 2), MESHFIX_FIX_ALL).r.self_intersections_remain == -1);
    const Result r = run(concat(sphere(1, 2), sphere(1, 2, 0.5, 0.3, 0.2)), kAll);
    CHECK(r.r.self_intersections_remain == 1 && r.r.self_intersecting_pairs > 0);
    // Two cubes that only touch do not count.
    CHECK(run(concat(cube(), cube(1, 1, 0, 0)), kAll).r.self_intersections_remain == 0);
}

void test_determinism() {
    std::puts("determinism");
    M m = sphere(2.0, 3);
    m = drop_faces(m, {5, 99, 100, 101, 400});
    m = concat(m, cube(1, 5, 5, 5));
    const Result a = run(m, kAll), b = run(m, kAll);
    CHECK(a.mesh.v == b.mesh.v && a.mesh.f == b.mesh.f);
}

void test_abi() {
    std::puts("ABI");
    CHECK(meshfix_abi_version() == MESHFIX_ABI_VERSION);
    CHECK(std::strcmp(meshfix_version(), MESHFIX_VERSION_STRING) == 0);
    const M c = drop_faces(cube(), {2, 3});
    meshfix_mesh *src = nullptr, *out = nullptr;
    CHECK(meshfix_mesh_create(c.v.data(), c.nv(), c.f.data(), c.nf(), &src) == MESHFIX_OK);

    // An older caller: a report struct that stops after the first counters, and a short options struct.
    struct {
        uint32_t struct_size;
        int32_t before, after;
        char canary[64];
    } small = {12, -1, -1, {}};
    std::memset(small.canary, 0x5A, sizeof small.canary);
    meshfix_options o;
    meshfix_options_init(&o);
    CHECK(meshfix_repair(src, &o, &out, reinterpret_cast<meshfix_report *>(&small)) == MESHFIX_OK);
    CHECK(small.before == 0 && small.after == 1 && small.canary[0] == 0x5A && small.canary[63] == 0x5A);
    meshfix_mesh_free(out);
    out = nullptr;

    struct {
        uint32_t struct_size, flags;
    } tiny = {8, MESHFIX_FIX_ALL};
    CHECK(meshfix_repair(src, reinterpret_cast<meshfix_options *>(&tiny), &out, nullptr) == MESHFIX_OK && out);
    meshfix_mesh_free(out);
    out = nullptr;
    tiny.struct_size = 4;
    CHECK(meshfix_repair(src, reinterpret_cast<meshfix_options *>(&tiny), &out, nullptr) == MESHFIX_ERR_INVALID_ARGUMENT && !out);

    // Argument checking and error strings.
    CHECK(meshfix_repair(nullptr, nullptr, &out, nullptr) == MESHFIX_ERR_INVALID_ARGUMENT);
    CHECK(meshfix_mesh_create(nullptr, 3, nullptr, 1, &out) == MESHFIX_ERR_INVALID_ARGUMENT);
    meshfix_mesh *empty = nullptr;
    CHECK(meshfix_mesh_create(nullptr, 0, nullptr, 0, &empty) == MESHFIX_OK);
    CHECK(meshfix_repair(empty, nullptr, &out, nullptr) == MESHFIX_ERR_EMPTY_MESH);
    CHECK(std::strlen(meshfix_last_error()) > 0);
    CHECK(std::strcmp(meshfix_status_string(MESHFIX_ERR_CANCELLED), "cancelled") == 0);
    meshfix_mesh_free(empty);
    meshfix_mesh_free(nullptr);

    // Borrowed arrays and the float constructor.
    CHECK(meshfix_mesh_vertex_count(src) == 8 && meshfix_mesh_face_count(src) == 10);
    const float fv[9] = {0, 0, 0, 1, 0, 0, 0, 1, 0};
    const uint32_t ff[3] = {0, 1, 2};
    meshfix_mesh *tri = nullptr;
    CHECK(meshfix_mesh_create_f32(fv, 3, ff, 1, &tri) == MESHFIX_OK);
    CHECK(meshfix_mesh_vertices(tri)[3] == 1.0);
    meshfix_mesh_free(tri);

    // Cancelling through the progress callback.
    meshfix_options po;
    meshfix_options_init(&po);
    po.progress = [](void *, const char *stage, double) { return std::strcmp(stage, "holes") == 0 ? 1 : 0; };
    CHECK(meshfix_repair(src, &po, &out, nullptr) == MESHFIX_ERR_CANCELLED && !out);

    // Analysis does not repair.
    meshfix_report rep;
    meshfix_report_init(&rep);
    CHECK(meshfix_analyze(src, nullptr, &rep) == MESHFIX_OK);
    CHECK(rep.watertight_before == 0 && rep.watertight_after == 0 && rep.boundary_edges_before == 4 && rep.output_faces == 10);

    // JSON: snprintf semantics.
    const size_t need = meshfix_report_to_json(&rep, nullptr, 0);
    std::vector<char> buf(need + 1);
    CHECK(meshfix_report_to_json(&rep, buf.data(), buf.size()) == need && std::strlen(buf.data()) == need);
    CHECK(std::string(buf.data()).find("\"watertight_before\": false") != std::string::npos);
    CHECK(meshfix_report_to_json(&rep, nullptr, 16) == need); // a NULL buffer is not written to
    char tinybuf[8];
    CHECK(meshfix_report_to_json(&rep, tinybuf, sizeof tinybuf) == need && std::strlen(tinybuf) == 7);
    meshfix_mesh_free(src);
}

void test_files() {
    std::puts("files");
    const std::string dir = std::getenv("MESHFIX_TEST_TMP") ? std::getenv("MESHFIX_TEST_TMP") : ".";
    const M ball = sphere(1.0, 2);
    meshfix_mesh *src = nullptr, *back = nullptr;
    CHECK(meshfix_mesh_create(ball.v.data(), ball.nv(), ball.f.data(), ball.nf(), &src) == MESHFIX_OK);
    const std::string stl = dir + "/meshfix_test.stl", obj = dir + "/meshfix_test.obj";
    CHECK(meshfix_mesh_write(src, stl.c_str()) == MESHFIX_OK);
    CHECK(meshfix_mesh_read(stl.c_str(), &back) == MESHFIX_OK);
    CHECK(meshfix_mesh_face_count(back) == ball.nf() && meshfix_mesh_vertex_count(back) == ball.nv()); // soup merged on load
    meshfix_mesh_free(back);
    CHECK(meshfix_mesh_write(src, obj.c_str()) == MESHFIX_OK);
    CHECK(meshfix_mesh_read(obj.c_str(), &back) == MESHFIX_OK && meshfix_mesh_face_count(back) == ball.nf());
    meshfix_mesh_free(back);
    CHECK(meshfix_mesh_read((dir + "/does-not-exist.stl").c_str(), &back) == MESHFIX_ERR_IO);
    CHECK(meshfix_mesh_read(stl.c_str(), nullptr) == MESHFIX_ERR_INVALID_ARGUMENT);
    // ASCII STL
    const std::string ascii = dir + "/meshfix_test_ascii.stl";
    if (FILE *f = std::fopen(ascii.c_str(), "w")) {
        std::fputs("solid t\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\nendloop\nendfacet\nendsolid t\n", f);
        std::fclose(f);
    }
    CHECK(meshfix_mesh_read(ascii.c_str(), &back) == MESHFIX_OK && meshfix_mesh_face_count(back) == 1);
    meshfix_mesh_free(back);
    // OBJ with inline comments and slashes.
    const std::string commented = dir + "/meshfix_test_comment.obj";
    if (FILE *f = std::fopen(commented.c_str(), "w")) {
        std::fputs("# header\nv 0 0 0\nv 1 0 0\nv 0 1 0 # corner\nf 1/1/1 2/2/2 3/3/3 # face\n", f);
        std::fclose(f);
    }
    CHECK(meshfix_mesh_read(commented.c_str(), &back) == MESHFIX_OK && meshfix_mesh_face_count(back) == 1);
    meshfix_mesh_free(back);
    std::remove(commented.c_str());
    std::remove(stl.c_str());
    std::remove(obj.c_str());
    std::remove(ascii.c_str());
    meshfix_mesh_free(src);
}

// Scenarios of the Snapmaker Orca fork's "Fix model" test suite (tests/libslic3r/test_meshboolean.cpp), which this
// library replaces there; the volumes and counts are the ones that suite expects.
M without_faces_above(const M &m, double z) {
    M out;
    out.v = m.v;
    for (size_t i = 0; i < m.nf(); ++i) {
        bool all_above = true;
        for (int k = 0; k < 3; ++k)
            all_above = all_above && m.v[3 * m.f[3 * i + k] + 2] > z;
        if (!all_above)
            out.add_face(m.f[3 * i], m.f[3 * i + 1], m.f[3 * i + 2]);
    }
    return out;
}

M pop_face(M m) {
    m.f.resize(m.f.size() - 3);
    return m;
}

void test_orca_parity() {
    std::puts("orca fork scenarios");
    const auto fixed_volume = [](const M &m) {
        const Result r = run(m, kAll);
        CHECK(r.status == MESHFIX_OK && r.r.watertight_after == 1);
        return r.r.volume_after;
    };
    // A hollow solid (inside-out inner cube) with a broken outer wall.
    {
        const M hollow = concat(pop_face(cube(10)), flip_all(cube(5, 2.5, 2.5, 2.5)));
        CHECK_NEAR(fixed_volume(hollow), 1000. - 125., 1.0);
    }
    // Two opposite sides missing: a square tube with two holes.
    {
        M tube;
        tube.v = cube(10).v;
        const M c = cube(10);
        for (size_t i = 0; i < c.nf(); ++i) {
            bool bottom = true, top = true;
            for (int k = 0; k < 3; ++k) {
                bottom = bottom && c.v[3 * c.f[3 * i + k] + 2] == 0.0;
                top = top && c.v[3 * c.f[3 * i + k] + 2] == 10.0;
            }
            if (!bottom && !top)
                tube.add_face(c.f[3 * i], c.f[3 * i + 1], c.f[3 * i + 2]);
        }
        const Result r = run(tube, kAll);
        CHECK(r.r.holes_filled == 2 && r.r.watertight_after == 1);
        CHECK_NEAR(r.r.volume_after, 1000., 1.0);
    }
    // A large hole in a curved surface: the patch loses at most the cap above the hole's ring.
    {
        const M ball = uv_sphere(5.0, 30, 60);
        const M capless = without_faces_above(ball, 4.0);
        double ring_z = -5;
        for (size_t i = 0; i < capless.nf() * 3; ++i)
            ring_z = std::max(ring_z, capless.v[3 * capless.f[i] + 2]);
        const double h = 5.0 - ring_z, cap = kPi * h * h * (3 * 5.0 - h) / 3;
        const double v = fixed_volume(capless);
        CHECK(v <= volume(ball) * 1.001 && v >= volume(ball) - cap);
    }
    // Many small holes: every 11th face of a sphere is missing.
    {
        const M ball = uv_sphere(5.0, 30, 60);
        M holed;
        holed.v = ball.v;
        for (size_t i = 0; i < ball.nf(); ++i)
            if (i % 11 != 0)
                holed.add_face(ball.f[3 * i], ball.f[3 * i + 1], ball.f[3 * i + 2]);
        CHECK_NEAR(fixed_volume(holed), volume(ball), 0.01 * volume(ball));
    }
    // An inside-out open mesh, a single inverted face.
    {
        M open = pop_face(cube(10));
        CHECK_NEAR(fixed_volume(flip_all(open)), 1000., 1.0);
        M one = cube(10);
        std::swap(one.f[1], one.f[2]);
        CHECK_NEAR(fixed_volume(one), 1000., 1.0);
    }
    // Unindexed soup and sub-micron seams: welding closes the cube without adding faces.
    {
        const M c = cube(10);
        M soup, noisy;
        unsigned seed = 3;
        for (size_t i = 0; i < c.nf(); ++i) {
            uint32_t a[3], b[3];
            for (int k = 0; k < 3; ++k) {
                const double *p = &c.v[3 * c.f[3 * i + k]];
                seed = seed * 1664525u + 1013904223u;
                const double n = ((seed >> 8) % 1000) / 1000.0 * 2e-7 - 1e-7;
                a[k] = soup.add_vertex(p[0], p[1], p[2]);
                b[k] = noisy.add_vertex(p[0] + n, p[1] - n, p[2] + n);
            }
            soup.add_face(a[0], a[1], a[2]);
            noisy.add_face(b[0], b[1], b[2]);
        }
        CHECK_NEAR(fixed_volume(soup), 1000., 1.0);
        const Result r = run(noisy, kAll);
        CHECK(r.mesh.nf() == 12 && r.r.watertight_after == 1);
    }
    // A zero-area sliver on the open border.
    {
        M m = pop_face(cube(10));
        const uint32_t a = m.f[m.f.size() - 3], b = m.f[m.f.size() - 2];
        m.add_face(a, b, b);
        CHECK_NEAR(fixed_volume(m), 1000., 1.0);
    }
    // Solids touching at a vertex / sharing an edge, each with one face missing.
    {
        CHECK_NEAR(fixed_volume(pop_face(concat(cube(10), cube(10, 10, 10, 10)))), 2000., 2.0);
        CHECK_NEAR(fixed_volume(pop_face(concat(cube(10), cube(10, 10, 10, 0)))), 2000., 2.0);
    }
    // Sub-millimetre, far from the origin, and so far out that the tolerance weld is skipped.
    {
        CHECK_NEAR(fixed_volume(pop_face(cube(0.2))), 0.008, 1e-5);
        const Result far = run(pop_face(cube(10, 1000, -1000, 500)), kAll);
        CHECK(far.r.watertight_after == 1);
        CHECK_NEAR(far.r.volume_after, 1000., 1.0);
        const double size = std::ldexp(1.0, 31), distance = std::ldexp(1.0, 54);
        CHECK_NEAR(fixed_volume(pop_face(cube(size, distance, distance, distance))) / std::ldexp(1.0, 93), 1.0, 0.001);
    }
    // A surface that encloses no volume leaves nothing: the caller reports failure.
    {
        M sheet;
        sheet.add_vertex(0, 0, 0);
        sheet.add_vertex(10, 0, 0);
        sheet.add_vertex(10, 10, 0);
        sheet.add_vertex(0, 10, 0);
        sheet.add_face(0, 1, 2);
        sheet.add_face(0, 2, 3);
        const Result r = run(sheet, kAll);
        CHECK(r.status == MESHFIX_OK && r.mesh.nf() == 0 && r.r.output_faces == 0);
    }
    // One closed shell with a corner pushed through the opposite face stays self-intersecting, and says so.
    {
        M m = cube(10);
        m.v[3 * 4] = 3;
        m.v[3 * 4 + 1] = 3;
        m.v[3 * 4 + 2] = -5;
        const Result r = run(m, kAll);
        CHECK(r.r.self_intersections_remain == 1);
    }
}

// Random soups on a tiny integer grid: coincident points, degenerate and duplicate faces, non-manifold edges and
// pinched vertices everywhere. The repair must never crash (run under ASan/UBSan in CI) and must return valid indices.
void test_fuzz() {
    std::puts("fuzz");
    unsigned seed = 12345;
    const auto rnd = [&seed](unsigned n) {
        seed = seed * 1664525u + 1013904223u;
        return (seed >> 8) % n;
    };
    for (int iter = 0; iter < 300; ++iter) {
        M m;
        const unsigned nv = 4 + rnd(30), nf = 1 + rnd(80), grid = 1 + rnd(4);
        for (unsigned i = 0; i < nv; ++i)
            m.add_vertex(rnd(grid + 1), rnd(grid + 1), rnd(grid + 1));
        for (unsigned i = 0; i < nf; ++i)
            m.add_face(rnd(nv), rnd(nv), rnd(nv));
        const Result r = run(m, kAll);
        CHECK(r.status == MESHFIX_OK);
        bool valid = r.mesh.f.size() % 3 == 0;
        for (uint32_t x : r.mesh.f)
            valid = valid && x < r.mesh.nv();
        CHECK(valid);
        const Result again = run(m, kAll);
        CHECK(again.mesh.v == r.mesh.v && again.mesh.f == r.mesh.f);
    }
    // A sphere with random faces removed, flipped and duplicated.
    for (int iter = 0; iter < 20; ++iter) {
        M m = sphere(1.0, 2);
        std::vector<size_t> drop;
        for (unsigned i = 0; i < 1 + rnd(30); ++i)
            drop.push_back(rnd(unsigned(m.nf())));
        m = drop_faces(m, drop);
        for (unsigned i = 0; i < rnd(20); ++i) {
            const size_t f = rnd(unsigned(m.nf()));
            std::swap(m.f[3 * f + 1], m.f[3 * f + 2]);
        }
        const Result r = run(m, kAll);
        CHECK(r.status == MESHFIX_OK && r.r.boundary_edges_after <= r.r.boundary_edges_before);
    }
}

} // namespace

int main() {
    test_clean_cube_is_untouched();
    test_holes();
    test_flipped_faces();
    test_duplicate_vertices();
    test_duplicate_and_degenerate_faces();
    test_back_to_back_faces_cancel();
    test_non_manifold_edges();
    test_t_junctions();
    test_islands_and_flat_shells();
    test_nested_shells();
    test_self_intersection_check();
    test_determinism();
    test_abi();
    test_files();
    test_orca_parity();
    test_fuzz();
    std::printf("%d checks, %d failed\n", g_checks, g_failures);
    return g_failures == 0 ? 0 : 1;
}
