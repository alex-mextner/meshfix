cmake_minimum_required(VERSION 3.16)
project(meshfix VERSION 0.1.0 LANGUAGES C CXX
        DESCRIPTION "Triangle mesh repair library with a stable C ABI")

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE Release CACHE STRING "" FORCE)
endif()

if(CMAKE_SOURCE_DIR STREQUAL CMAKE_CURRENT_SOURCE_DIR)
  set(MESHFIX_TOPLEVEL ON)
else()
  set(MESHFIX_TOPLEVEL OFF)
endif()

option(MESHFIX_BUILD_SHARED "Build the shared library" ON)
option(MESHFIX_BUILD_STATIC "Build the static library" ON)
option(MESHFIX_BUILD_CLI "Build the meshfix command line tool" ${MESHFIX_TOPLEVEL})
option(MESHFIX_BUILD_TESTS "Build the CTest suite" ${MESHFIX_TOPLEVEL})
option(MESHFIX_INSTALL "Generate install rules" ${MESHFIX_TOPLEVEL})

set(MESHFIX_SOURCES
  src/capi.cpp src/cleanup.cpp src/components.cpp src/edges.cpp src/holes.cpp
  src/io.cpp src/nonmanifold.cpp src/repair.cpp src/selfint.cpp)

function(meshfix_target_common tgt)
  target_include_directories(${tgt} PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
                                           $<INSTALL_INTERFACE:include>)
  target_include_directories(${tgt} PRIVATE src)
  target_compile_features(${tgt} PUBLIC cxx_std_17)
  set_target_properties(${tgt} PROPERTIES CXX_VISIBILITY_PRESET hidden VISIBILITY_INLINES_HIDDEN ON
                                          POSITION_INDEPENDENT_CODE ON)
  if(MSVC)
    target_compile_options(${tgt} PRIVATE /W4 /permissive-)
  else()
    target_compile_options(${tgt} PRIVATE -Wall -Wextra -Wpedantic)
  endif()
endfunction()

set(MESHFIX_INSTALL_TARGETS "")

if(MESHFIX_BUILD_SHARED OR SKBUILD)
  add_library(meshfix SHARED ${MESHFIX_SOURCES})
  add_library(meshfix::meshfix ALIAS meshfix)
  meshfix_target_common(meshfix)
  target_compile_definitions(meshfix PRIVATE MESHFIX_BUILDING)
  set_target_properties(meshfix PROPERTIES VERSION ${PROJECT_VERSION} SOVERSION 1)
  list(APPEND MESHFIX_INSTALL_TARGETS meshfix)
endif()

if(MESHFIX_BUILD_STATIC AND NOT SKBUILD)
  add_library(meshfix_static STATIC ${MESHFIX_SOURCES})
  add_library(meshfix::meshfix_static ALIAS meshfix_static)
  meshfix_target_common(meshfix_static)
  target_compile_definitions(meshfix_static PUBLIC MESHFIX_STATIC_DEFINE)
  if(NOT WIN32)
    set_target_properties(meshfix_static PROPERTIES OUTPUT_NAME meshfix)
  endif()
  list(APPEND MESHFIX_INSTALL_TARGETS meshfix_static)
endif()

if(NOT TARGET meshfix AND TARGET meshfix_static)
  add_library(meshfix::meshfix ALIAS meshfix_static)
endif()

# Python wheel (scikit-build-core): ship only the shared library, next to the ctypes loader.
if(SKBUILD)
  install(TARGETS meshfix LIBRARY DESTINATION meshfix RUNTIME DESTINATION meshfix)
  return()
endif()

if(MESHFIX_BUILD_CLI)
  add_executable(meshfix_cli cli/main.cpp)
  set_target_properties(meshfix_cli PROPERTIES OUTPUT_NAME meshfix)
  if(TARGET meshfix_static)
    target_link_libraries(meshfix_cli PRIVATE meshfix_static)
  else()
    target_link_libraries(meshfix_cli PRIVATE meshfix)
  endif()
  if(MSVC)
    target_compile_options(meshfix_cli PRIVATE /W4)
  else()
    target_compile_options(meshfix_cli PRIVATE -Wall -Wextra -Wpedantic)
  endif()
endif()

if(MESHFIX_BUILD_TESTS)
  enable_testing()
  add_subdirectory(tests)
endif()

if(MESHFIX_INSTALL)
  include(GNUInstallDirs)
  include(CMakePackageConfigHelpers)
  install(TARGETS ${MESHFIX_INSTALL_TARGETS} EXPORT meshfixTargets
          LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
          ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
          RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
          INCLUDES DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})
  if(TARGET meshfix_cli)
    install(TARGETS meshfix_cli RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR})
  endif()
  install(FILES include/meshfix.h DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})
  install(EXPORT meshfixTargets NAMESPACE meshfix:: DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/meshfix)
  configure_package_config_file(cmake/meshfixConfig.cmake.in ${CMAKE_CURRENT_BINARY_DIR}/meshfixConfig.cmake
                                INSTALL_DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/meshfix)
  write_basic_package_version_file(${CMAKE_CURRENT_BINARY_DIR}/meshfixConfigVersion.cmake
                                   VERSION ${PROJECT_VERSION} COMPATIBILITY SameMajorVersion)
  install(FILES ${CMAKE_CURRENT_BINARY_DIR}/meshfixConfig.cmake ${CMAKE_CURRENT_BINARY_DIR}/meshfixConfigVersion.cmake
          DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/meshfix)
endif()
