# DiscSplitter's Blu-ray engine: tsMuxeR built from the source snapshot in tsmuxer/ (see UPSTREAM.md).
#
# Only the command line program is built, statically linked (no MSVC runtime or zlib DLL to ship),
# with zlib from third_party/zlib. Built by engine/build_engine.py; the result is engine/bin/tsMuxeR.exe.
cmake_minimum_required(VERSION 3.20)

# The upstream CMakeLists ask for CMake 3.10, which leaves the MSVC runtime policy unset there;
# this makes every target, theirs included, use the static runtime (/MT).
set(CMAKE_POLICY_DEFAULT_CMP0091 NEW)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")

project(discsplitter_engine C CXX)

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED TRUE)
set(CMAKE_CXX_EXTENSIONS FALSE)

# What upstream's top-level CMakeLists sets for its subprojects.
set(UPSTREAM_COMMIT "ea5b37f" CACHE STRING "tsMuxeR commit the snapshot was taken from")
add_definitions("-DTSMUXER_VERSION=\"3.1.0 (DiscSplitter, ${UPSTREAM_COMMIT})\"")
set(CMAKE_INSTALL_BINDIR bin)
if(MSVC)
  add_compile_options("/utf-8" "/MP")
  add_definitions(-D_CRT_SECURE_NO_WARNINGS)
endif()
if(WIN32)
  add_definitions(-DUNICODE -D_UNICODE)
endif()

# zlib, compiled here: upstream finds it with find_package(ZLIB), which is answered by cmake/FindZLIB.cmake.
file(GLOB ZLIB_SOURCES "${CMAKE_CURRENT_SOURCE_DIR}/third_party/zlib/*.c")
add_library(engine_zlib STATIC ${ZLIB_SOURCES})
target_include_directories(engine_zlib PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/third_party/zlib")
if(MSVC)
  target_compile_options(engine_zlib PRIVATE /W0)
endif()
list(PREPEND CMAKE_MODULE_PATH "${CMAKE_CURRENT_SOURCE_DIR}/cmake")
set(WITHOUT_PKGCONFIG ON)

add_subdirectory(tsmuxer/libmediation libmediation)
add_subdirectory(tsmuxer/tsMuxer tsMuxer)
set_target_properties(tsmuxer PROPERTIES OUTPUT_NAME tsMuxeR)
