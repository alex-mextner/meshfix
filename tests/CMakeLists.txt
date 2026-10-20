add_executable(meshfix_tests test_meshfix.cpp)
if(TARGET meshfix_static)
  target_link_libraries(meshfix_tests PRIVATE meshfix_static)
else()
  target_link_libraries(meshfix_tests PRIVATE meshfix)
endif()
target_compile_options(meshfix_tests PRIVATE $<$<NOT:$<CXX_COMPILER_ID:MSVC>>:-Wall -Wextra>)
add_test(NAME meshfix_c_api COMMAND meshfix_tests)
set_tests_properties(meshfix_c_api PROPERTIES ENVIRONMENT "MESHFIX_TEST_TMP=${CMAKE_CURRENT_BINARY_DIR}")

# The C example doubles as a check that the header compiles as plain C and works end to end.
add_executable(meshfix_example_c ${PROJECT_SOURCE_DIR}/examples/example.c)
if(TARGET meshfix_static)
  target_link_libraries(meshfix_example_c PRIVATE meshfix_static)
else()
  target_link_libraries(meshfix_example_c PRIVATE meshfix)
endif()
add_test(NAME meshfix_example_c COMMAND meshfix_example_c)

find_package(Python3 COMPONENTS Interpreter)
if(Python3_FOUND AND TARGET meshfix)
  add_test(NAME meshfix_python
           COMMAND ${Python3_EXECUTABLE} -m pytest ${PROJECT_SOURCE_DIR}/tests/python -q -p no:cacheprovider
           WORKING_DIRECTORY ${PROJECT_SOURCE_DIR})
  set_tests_properties(meshfix_python PROPERTIES ENVIRONMENT "MESHFIX_LIBRARY=$<TARGET_FILE:meshfix>")
  if(TARGET meshfix_cli)
    set_property(TEST meshfix_python APPEND PROPERTY ENVIRONMENT "MESHFIX_CLI=$<TARGET_FILE:meshfix_cli>")
  endif()
  add_test(NAME meshfix_python_example COMMAND ${Python3_EXECUTABLE} ${PROJECT_SOURCE_DIR}/examples/example.py)
  set_tests_properties(meshfix_python_example PROPERTIES
    ENVIRONMENT "MESHFIX_LIBRARY=$<TARGET_FILE:meshfix>;PYTHONPATH=${PROJECT_SOURCE_DIR}/python")
endif()
