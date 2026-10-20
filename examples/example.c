/* Repairs a unit cube that is missing its top face, through the C ABI only. */
#include <stdio.h>
#include <stdlib.h>

#include "meshfix.h"

int main(void) {
    const double vertices[] = {0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0, 0, 0, 1, 1, 0, 1, 1, 1, 1, 0, 1, 1};
    /* 10 triangles: the top quad (4, 5, 6, 7) is missing */
    const uint32_t faces[] = {0, 3, 2, 0, 2, 1, 0, 1, 5, 0, 5, 4, 3, 7, 6, 3, 6, 2, 0, 4, 7, 0, 7, 3, 1, 2, 6, 1, 6, 5};

    meshfix_mesh *in = NULL, *out = NULL;
    if (meshfix_mesh_create(vertices, 8, faces, 10, &in) != MESHFIX_OK) {
        fprintf(stderr, "create: %s\n", meshfix_last_error());
        return 2;
    }

    meshfix_options options;
    meshfix_options_init(&options); /* defaults + struct_size */
    meshfix_report report;
    meshfix_report_init(&report);

    meshfix_status status = meshfix_repair(in, &options, &out, &report);
    if (status != MESHFIX_OK) {
        fprintf(stderr, "repair: %s (%s)\n", meshfix_status_string(status), meshfix_last_error());
        meshfix_mesh_free(in);
        return 2;
    }

    printf("meshfix %s\n", meshfix_version());
    printf("faces %zu -> %zu, watertight %d -> %d, volume %g -> %g, holes filled %llu\n", (size_t)report.input_faces,
           meshfix_mesh_face_count(out), report.watertight_before, report.watertight_after, report.volume_before,
           report.volume_after, (unsigned long long)report.holes_filled);

    char json[2048];
    meshfix_report_to_json(&report, json, sizeof json);
    printf("%s\n", json);

    const int ok = report.watertight_after && meshfix_mesh_face_count(out) == 12;
    meshfix_mesh_free(in);
    meshfix_mesh_free(out);
    return ok ? 0 : 1;
}
