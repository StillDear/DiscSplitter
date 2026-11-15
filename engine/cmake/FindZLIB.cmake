# Answers upstream's find_package(ZLIB) with the zlib compiled by engine/CMakeLists.txt.
set(ZLIB_FOUND TRUE)
set(ZLIB_INCLUDE_DIRS "${CMAKE_CURRENT_LIST_DIR}/../third_party/zlib")
set(ZLIB_LIBRARIES engine_zlib)
set(ZLIB_VERSION_STRING "1.3.1")
