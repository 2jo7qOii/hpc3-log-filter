# ============================================================================
#  Makefile —— HPC-3 日志压缩与稳定筛选优化
#
#  与 CMakeLists.txt 等价的构建入口，产物路径也保持一致：
#      make                 → build/log_filter（平台用法示例中的名字）
#                             build/optimized（同一实现的旧名副本）
#      make baseline        → build/baseline（原始基线，仅对照）
#      make test            → 公开测试 + 自建回归测试
#      make clean           → 删除 build/
#
#  编译口径固定为题目要求的 -O2 -std=c++17 -pthread。
# ============================================================================
CXX      ?= g++
CXXFLAGS ?= -O2 -std=c++17 -pthread
PYTHON   ?= python3

.PHONY: all baseline test clean

all: build/log_filter build/optimized

build/log_filter: optimized.cpp support.hpp
	@mkdir -p build
	$(CXX) $(CXXFLAGS) optimized.cpp -o $@

# 旧名副本：同一份二进制，行为完全一致，方便按名字查找可执行文件的脚本
build/optimized: build/log_filter
	cp -f build/log_filter build/optimized

build/baseline: bench/baseline.cpp src/support.hpp
	@mkdir -p build
	$(CXX) $(CXXFLAGS) -I src bench/baseline.cpp -o $@

baseline: build/baseline

test: all
	$(PYTHON) tests/test_public.py build/log_filter
	$(PYTHON) tests/test_regression.py build/log_filter

clean:
	rm -rf build
