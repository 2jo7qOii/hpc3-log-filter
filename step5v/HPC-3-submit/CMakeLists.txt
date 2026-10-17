# ============================================================================
#  CMakeLists.txt —— HPC-3 日志压缩与稳定筛选优化
#
#  说明：本工程原本用 g++ 直接编译（见 requirements.txt），此文件提供等价的
#        CMake 构建方式，方便按目录规范要求一键构建：
#
#          cmake -S . -B build && cmake --build build
#
#        产物为项目根目录下的 build/optimized 与 build/baseline，
#        与手工编译的 bench/optimized、bench/baseline 功能完全一致。
#
#  仅使用 CMake 最基础的命令（不依赖任何第三方包、不需要联网）。
# ============================================================================
cmake_minimum_required(VERSION 3.10)
project(hpc3_log_filter LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

# 优化实现：src/optimized.cpp（默认 --impl single；--impl twopass 可对比两遍分块实现）
add_executable(optimized src/optimized.cpp)
target_include_directories(optimized PRIVATE src)
find_package(Threads REQUIRED)
target_link_libraries(optimized PRIVATE Threads::Threads)

# 原始基线（仅作对照，不参与评测）：优先用根目录的 baseline.cpp，
# 缺失则回退到 bench/baseline.cpp。两者与平台提供的 baseline.cpp 逐字节一致。
if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/baseline.cpp")
  set(HPC3_BASELINE_SRC "${CMAKE_CURRENT_SOURCE_DIR}/baseline.cpp")
else()
  set(HPC3_BASELINE_SRC "${CMAKE_CURRENT_SOURCE_DIR}/bench/baseline.cpp")
endif()
add_executable(baseline "${HPC3_BASELINE_SRC}")
target_include_directories(baseline PRIVATE src)

# 安装到 CMAKE_INSTALL_PREFIX/bin（该前缀是 CMake 的变量，不是硬编码绝对路径）
install(TARGETS optimized baseline RUNTIME DESTINATION bin)

# ---------------------------------------------------------------------------
#  测试（可选）：ctest 会依次运行公开测试与自建回归测试。
#  启用方式：cmake -S . -B build -DENABLE_TESTS=ON && ctest --test-dir build
#  注意：两个测试脚本按"可执行文件路径"作为参数调用被测程序。
# ---------------------------------------------------------------------------
option(ENABLE_TESTS "Register python test scripts with ctest" OFF)
if(ENABLE_TESTS)
  enable_testing()
  find_package(Python3 COMPONENTS Interpreter)
  if(Python3_Interpreter_FOUND)
    add_test(NAME public_tests
             COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_public.py
                     $<TARGET_FILE:optimized>)
    add_test(NAME regression_tests
             COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_regression.py
                     $<TARGET_FILE:optimized>)
  else()
    message(STATUS "未找到 Python3 解释器，跳过测试注册（公开测试可用 python3 tests/test_public.py 手工运行）")
  endif()
endif()
