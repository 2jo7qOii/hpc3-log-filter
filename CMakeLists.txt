# ============================================================================
#  CMakeLists.txt —— HPC-3 日志压缩与稳定筛选优化
#
#  一键构建：
#      cmake -S . -B build && cmake --build build
#
#  默认产物（同一份源码、行为完全一致）：
#      build/log_filter        ← 优化实现，平台用这个名字跑公开测试
#      build/optimized         ← 旧名兼容（方便按名字查找二进制的脚本）
#  按需产物（不进入默认构建）：
#      cmake --build build --target baseline    → build/baseline （原始基线，仅对照）
#
#  编译口径与 g++ 手工路径一致：-O2 -std=c++17 -pthread。
#  仅使用 CMake 最基础的命令（不依赖第三方包、不需要联网）。
# ============================================================================
cmake_minimum_required(VERSION 3.10)
project(hpc3_log_filter LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()
# 题目指定的编译口径是 -O2；不让 CMake 的 Release 默认 -O3 改变实验条件。
set(CMAKE_CXX_FLAGS_RELEASE "-O2 -DNDEBUG")

# 源码发现：优先根目录的 optimized.cpp（提交包布局），其次 src/optimized.cpp
#（开发仓库布局）。两种布局内容逐字节相同，见 bench/package.sh 的自检。
if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/optimized.cpp")
  set(HPC3_MAIN_SOURCE "${CMAKE_CURRENT_SOURCE_DIR}/optimized.cpp")
  set(HPC3_INCLUDE_DIR "${CMAKE_CURRENT_SOURCE_DIR}")
else()
  set(HPC3_MAIN_SOURCE "${CMAKE_CURRENT_SOURCE_DIR}/src/optimized.cpp")
  set(HPC3_INCLUDE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/src")
endif()

find_package(Threads REQUIRED)

# 平台约定：评测二进制的名字是 log_filter（见 tests/test_public.py 的用法示例）。
# 同时保留旧名 optimized——两者由同一份源码编译、行为完全一致，方便按名字查找
# 可执行文件的 checker；原始基线 baseline 不进入默认构建，避免被误当成提交实现。
add_executable(log_filter "${HPC3_MAIN_SOURCE}")
target_include_directories(log_filter PRIVATE "${HPC3_INCLUDE_DIR}")
target_link_libraries(log_filter PRIVATE Threads::Threads)

add_executable(optimized "${HPC3_MAIN_SOURCE}")
target_include_directories(optimized PRIVATE "${HPC3_INCLUDE_DIR}")
target_link_libraries(optimized PRIVATE Threads::Threads)

# 原始基线（只作对照，不参与评测），显式构建：cmake --build build --target baseline
if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/baseline.cpp")
  set(HPC3_BASELINE_SRC "${CMAKE_CURRENT_SOURCE_DIR}/baseline.cpp")
else()
  set(HPC3_BASELINE_SRC "${CMAKE_CURRENT_SOURCE_DIR}/bench/baseline.cpp")
endif()
if(EXISTS "${HPC3_BASELINE_SRC}")
  add_executable(baseline EXCLUDE_FROM_ALL "${HPC3_BASELINE_SRC}")
  target_include_directories(baseline PRIVATE "${HPC3_INCLUDE_DIR}")
endif()

install(TARGETS log_filter optimized RUNTIME DESTINATION bin)

# ---------------------------------------------------------------------------
#  测试：默认注册，ctest 会运行平台公开测试与本项目新增的回归测试。
#      cmake -S . -B build && cmake --build build && ctest --test-dir build
#  若环境没有 Python3，则自动跳过测试注册（不影响构建）。
# ---------------------------------------------------------------------------
option(ENABLE_TESTS "Register python test scripts with ctest" ON)
if(ENABLE_TESTS)
  enable_testing()
  find_package(Python3 COMPONENTS Interpreter QUIET)
  if(Python3_Interpreter_FOUND)
    add_test(NAME public_tests
             COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_public.py
                     $<TARGET_FILE:log_filter>)
    add_test(NAME regression_tests
             COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_regression.py
                     $<TARGET_FILE:log_filter>)
  else()
    message(STATUS "未找到 Python3，跳过测试注册（可直接运行 tests/test_public.py）")
  endif()
endif()

message(STATUS "默认产物: ${CMAKE_CURRENT_BINARY_DIR}/log_filter 与 optimized（-O2 -std=c++17 -pthread）")
