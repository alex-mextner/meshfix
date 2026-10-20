# Contributing

- Build and test: `cmake -S . -B build && cmake --build build -j && ctest --test-dir build --output-on-failure`,
  then `MESHFIX_LIBRARY=$PWD/build/libmeshfix.so python -m pytest tests/python -q`.
- Every repair gets a generated defective mesh in `tests/test_meshfix.cpp` AND `tests/python/test_meshfix.py` that
  also runs with the repair disabled and shows the defect is still there. No third-party model files in the repo.
- The C ABI in `include/meshfix.h` only grows: append struct fields and functions, never reorder or remove, and
  keep `struct_size` handling. Breaking it needs `MESHFIX_ABI_VERSION` + a major version.
- Contributions are accepted under the MIT licence of this repository.
