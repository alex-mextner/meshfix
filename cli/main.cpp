// meshfix command line: meshfix in.stl -o out.stl --report json
// SPDX-License-Identifier: MIT
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include "meshfix.h"

namespace {

struct FixName {
    const char *name;
    uint32_t flag;
};
const FixName kFixes[] = {
    {"weld", MESHFIX_FIX_WELD},
    {"degenerate", MESHFIX_FIX_DEGENERATE},
    {"duplicate-faces", MESHFIX_FIX_DUPLICATE_FACES},
    {"t-junctions", MESHFIX_FIX_T_JUNCTIONS},
    {"orientation", MESHFIX_FIX_ORIENTATION},
    {"non-manifold", MESHFIX_FIX_NON_MANIFOLD},
    {"holes", MESHFIX_FIX_HOLES},
    {"components", MESHFIX_FIX_COMPONENTS},
    {"nested-shells", MESHFIX_FIX_NESTED_SHELLS},
    {"separate", MESHFIX_FIX_SEPARATE},
};

void usage(FILE *to) {
    std::fputs(
        "usage: meshfix <input.stl|.obj> [-o output.stl|.obj] [options]\n"
        "\n"
        "Repairs a triangle mesh: welds vertices, drops degenerate and duplicate faces, stitches\n"
        "T-junctions, orients faces outward, splits non-manifold edges, fills holes, removes islands.\n"
        "\n"
        "options:\n"
        "  -o, --output FILE            write the repaired mesh (without it nothing is written)\n"
        "      --report json|text|none  report on stdout (default text; json is machine readable)\n"
        "      --analyze                only inspect the input, do not repair\n"
        "      --weld-tolerance X       weld distance in model units (default auto, 0 = exact only)\n"
        "      --max-hole-edges N       leave holes with more boundary edges open (default: fill all)\n"
        "      --min-component-faces N  drop shells with fewer faces (default 8)\n"
        "      --no-<fix>               skip one repair: weld, degenerate, duplicate-faces, t-junctions,\n"
        "                               orientation, non-manifold, holes, components, nested-shells, separate\n"
        "      --separation X           distance touching vertex copies are nudged apart (default auto)\n"
        "      --only <fix>[,<fix>...]  run only the listed repairs\n"
        "      --no-self-intersection-check\n"
        "      --progress               print the stages on stderr\n"
        "      --version, -h/--help\n"
        "\n"
        "exit status: 0 the result is watertight, 1 it is not, 2 usage or I/O error\n",
        to);
}

int progress_cb(void *, const char *stage, double fraction) {
    std::fprintf(stderr, "[%3.0f%%] %s\n", fraction * 100.0, stage);
    return 0;
}

bool flag_for(const std::string &name, uint32_t &flag) {
    for (const FixName &f : kFixes)
        if (name == f.name) {
            flag = f.flag;
            return true;
        }
    return false;
}

void print_text(const meshfix_report &r) {
    std::printf("faces            %llu -> %llu\n", (unsigned long long)r.input_faces, (unsigned long long)r.output_faces);
    std::printf("vertices         %llu -> %llu (merged %llu)\n", (unsigned long long)r.input_vertices, (unsigned long long)r.output_vertices,
                (unsigned long long)r.vertices_merged);
    std::printf("watertight       %s -> %s\n", r.watertight_before ? "yes" : "no", r.watertight_after ? "yes" : "no");
    std::printf("manifold         %s -> %s\n", r.manifold_before ? "yes" : "no", r.manifold_after ? "yes" : "no");
    std::printf("volume           %.6g -> %.6g\n", r.volume_before, r.volume_after);
    std::printf("boundary edges   %llu -> %llu\n", (unsigned long long)r.boundary_edges_before, (unsigned long long)r.boundary_edges_after);
    std::printf("non-manifold e.  %llu -> %llu (vertex copies %llu)\n", (unsigned long long)r.non_manifold_edges_before,
                (unsigned long long)r.non_manifold_edges_after, (unsigned long long)r.non_manifold_vertices_split);
    std::printf("removed faces    invalid %llu, degenerate %llu, duplicate %llu\n", (unsigned long long)r.invalid_faces_removed,
                (unsigned long long)r.degenerate_faces_removed, (unsigned long long)r.duplicate_faces_removed);
    std::printf("t-junctions      %llu\n", (unsigned long long)r.t_junctions_fixed);
    std::printf("separated        %llu vertex copies\n", (unsigned long long)r.vertices_separated);
    std::printf("flipped faces    %llu\n", (unsigned long long)r.faces_flipped);
    std::printf("holes            found %llu, filled %llu, skipped %llu (+%llu faces)\n", (unsigned long long)r.holes_found,
                (unsigned long long)r.holes_filled, (unsigned long long)r.holes_skipped, (unsigned long long)r.hole_faces_added);
    std::printf("components       %llu -> %llu (small removed %llu, flat removed %llu, cavities %llu)\n",
                (unsigned long long)r.components_before, (unsigned long long)r.components_after,
                (unsigned long long)r.small_components_removed, (unsigned long long)r.flat_components_removed,
                (unsigned long long)r.cavity_shells);
    if (r.self_intersections_remain >= 0)
        std::printf("self-intersect.  %s (%llu pairs)\n", r.self_intersections_remain ? "yes" : "no", (unsigned long long)r.self_intersecting_pairs);
    std::printf("time             %.1f ms\n", r.elapsed_ms);
}

} // namespace

int main(int argc, char **argv) {
    std::string input, output, report_mode = "text";
    bool analyze = false, progress = false;
    meshfix_options opts;
    meshfix_options_init(&opts);
    uint32_t only = 0;
    uint32_t disabled = 0;
    for (int i = 1; i < argc; ++i) {
        const std::string a = argv[i];
        const auto value = [&](const char *name) -> const char * {
            if (i + 1 >= argc) {
                std::fprintf(stderr, "meshfix: %s needs a value\n", name);
                std::exit(2);
            }
            return argv[++i];
        };
        if (a == "-h" || a == "--help") {
            usage(stdout);
            return 0;
        } else if (a == "--version") {
            std::printf("meshfix %s (ABI %u)\n", meshfix_version(), meshfix_abi_version());
            return 0;
        } else if (a == "-o" || a == "--output") {
            output = value("--output");
        } else if (a == "--report") {
            report_mode = value("--report");
            if (report_mode != "json" && report_mode != "text" && report_mode != "none") {
                std::fprintf(stderr, "meshfix: --report takes json, text or none\n");
                return 2;
            }
        } else if (a == "--analyze") {
            analyze = true;
        } else if (a == "--weld-tolerance") {
            opts.weld_tolerance = std::atof(value("--weld-tolerance"));
        } else if (a == "--separation") {
            opts.separation = std::atof(value("--separation"));
        } else if (a == "--max-hole-edges") {
            opts.max_hole_edges = uint32_t(std::strtoul(value("--max-hole-edges"), nullptr, 10));
        } else if (a == "--min-component-faces") {
            opts.min_component_faces = uint32_t(std::strtoul(value("--min-component-faces"), nullptr, 10));
        } else if (a == "--only") {
            std::string list = value("--only");
            size_t pos = 0;
            while (pos <= list.size()) {
                const size_t comma = list.find(',', pos);
                const std::string name = list.substr(pos, comma == std::string::npos ? std::string::npos : comma - pos);
                uint32_t flag;
                if (!flag_for(name, flag)) {
                    std::fprintf(stderr, "meshfix: unknown repair '%s'\n", name.c_str());
                    return 2;
                }
                only |= flag;
                if (comma == std::string::npos)
                    break;
                pos = comma + 1;
            }
        } else if (a == "--no-self-intersection-check") {
            opts.flags &= ~uint32_t(MESHFIX_CHECK_SELF_INTERSECTIONS);
        } else if (a == "--progress") {
            progress = true;
        } else if (a.rfind("--no-", 0) == 0) {
            uint32_t flag;
            if (!flag_for(a.substr(5), flag)) {
                std::fprintf(stderr, "meshfix: unknown option %s\n", a.c_str());
                return 2;
            }
            disabled |= flag;
        } else if (!a.empty() && a[0] == '-') {
            std::fprintf(stderr, "meshfix: unknown option %s\n", a.c_str());
            return 2;
        } else if (input.empty()) {
            input = a;
        } else {
            std::fprintf(stderr, "meshfix: more than one input file\n");
            return 2;
        }
    }
    if (input.empty()) {
        usage(stderr);
        return 2;
    }
    if (only)
        opts.flags = (opts.flags & ~uint32_t(MESHFIX_FIX_ALL)) | only;
    opts.flags &= ~disabled;
    if (progress) {
        opts.progress = progress_cb;
    }

    meshfix_mesh *mesh = nullptr;
    meshfix_status st = meshfix_mesh_read(input.c_str(), &mesh);
    if (st != MESHFIX_OK) {
        std::fprintf(stderr, "meshfix: %s: %s\n", meshfix_status_string(st), meshfix_last_error());
        return 2;
    }
    meshfix_report report;
    meshfix_report_init(&report);
    meshfix_mesh *fixed = nullptr;
    if (analyze) {
        st = meshfix_analyze(mesh, &opts, &report);
    } else {
        st = meshfix_repair(mesh, &opts, &fixed, &report);
    }
    if (st != MESHFIX_OK) {
        std::fprintf(stderr, "meshfix: %s: %s\n", meshfix_status_string(st), meshfix_last_error());
        meshfix_mesh_free(mesh);
        return 2;
    }
    if (!output.empty() && fixed) {
        st = meshfix_mesh_write(fixed, output.c_str());
        if (st != MESHFIX_OK) {
            std::fprintf(stderr, "meshfix: %s: %s\n", meshfix_status_string(st), meshfix_last_error());
            meshfix_mesh_free(mesh);
            meshfix_mesh_free(fixed);
            return 2;
        }
    }
    if (report_mode == "json") {
        const size_t need = meshfix_report_to_json(&report, nullptr, 0);
        std::vector<char> buf(need + 1);
        meshfix_report_to_json(&report, buf.data(), buf.size());
        std::printf("%s\n", buf.data());
    } else if (report_mode == "text") {
        print_text(report);
    }
    const int code = report.watertight_after ? 0 : 1;
    meshfix_mesh_free(mesh);
    meshfix_mesh_free(fixed);
    return code;
}
