"""Repairs a unit cube that is missing its top face, through the Python API."""
import numpy as np

import meshfix

vertices = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], float)
faces = np.array([[0, 3, 2], [0, 2, 1], [0, 1, 5], [0, 5, 4], [3, 7, 6], [3, 6, 2], [0, 4, 7], [0, 7, 3],
                  [1, 2, 6], [1, 6, 5]])  # the top quad is missing

fixed_vertices, fixed_faces, report = meshfix.repair(vertices, faces)
print(f"meshfix {meshfix.version()}")
print(f"faces {report.input_faces} -> {report.output_faces}, watertight {report.watertight_before} -> "
      f"{report.watertight_after}, volume {report.volume_before:g} -> {report.volume_after:g}, "
      f"holes filled {report.holes_filled}")
assert report.watertight_after and len(fixed_faces) == 12
