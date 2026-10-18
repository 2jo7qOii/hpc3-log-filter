# HPC-3 日志压缩与稳定筛选优化

在**保持输入顺序**的前提下按查询筛选日志记录（全部字段保留、重复不去重、稳定输出），
并针对本机实测出的瓶颈——**数据相关的条件写出分支**——做了循环级优化。

## 结果概要

| 项目 | 结果 |
|---|---|
| 正确性 | 公开测试 7/7、自建回归 7/7、60 组参数化差分 0 失败、5 个数据集输出与基线**逐字节一致** |
| 加速比（1M/10M，random，50% 命中） | **1.7~2.2×**（逐样本交替 + 配对符号检验，p < 0.01） |
| 0% 命中（纯判断） | 约 **2.0~2.7×**（收益最大端） |
| 100% 命中（退化为整块拷贝） | 约 **0.9~1.0×**（分支方向恒定，优化无从发挥） |
| blocks / 90%（分支极易预测） | 约 **1.0~1.1×**（几乎无差异） |

> 收益来自消除"要不要写出"的数据相关分支（消融实验贡献 >95%），
> 而不是谓词改写或阈值局部化（两者实测贡献 ≈0）。详见 `REPORT.md` 第 7.3 节。

## 目录

| 路径 | 内容 |
|---|---|
| `optimized.cpp` | **根目录唯一的 C++ 源文件**：评测实现（`filter_records` + 外壳 `main`） |
| `support.hpp` | 平台提供的结构体与编解码（逐字节未改） |
| `CMakeLists.txt` | 目录规范要求的构建入口，默认产出 `build/log_filter` 与 `build/optimized` |
| `Makefile` | 等价的 make 入口，产物路径与 CMake 相同 |
| `README.md` | 本文件（构建、运行、测试、复现） |
| `requirements.txt` | 依赖与全部命令的速查（无第三方库） |
| `REPORT.md` / `REPORT-SUMMARY.md` | 完整实验报告（A4 排版版）/ 精简版 |
| `report.pdf` | 完整报告的 PDF（可直接打印/评审） |
| `src/` | 与根目录逐字节相同的工程布局副本（报告复现命令使用） |
| `bench/` | 原始基线 `baseline.cpp`、复现脚本、消融与差分工具 |
| `tests/` | 平台公开测试（逐字节未改）+ 自建回归测试 |
| `results/` | 原始测量样本、输入/输出指纹、图表等实验证据 |

> 根目录刻意只放**一个** `.cpp`：原始基线保留在 `bench/baseline.cpp`，这样即使
> checker 用 `g++ *.cpp` 这类通配方式编译，也不会撞上两个 `main`。

## 构建

```bash
# 方式一（推荐，与目录规范一致）：产出 build/log_filter（平台用法示例中的名字）
# 以及同源的 build/optimized（旧名兼容），两者行为完全一致
cmake -S . -B build && cmake --build build
#   需要基线时再显式构建：
#   cmake --build build --target baseline     → build/baseline

# 方式二：手工单文件编译（与 CMake 完全相同的编译口径）
mkdir -p build
g++ -O2 -std=c++17 -pthread optimized.cpp -o build/log_filter

# 方式三：make（产物路径与 CMake 一致）
make                 # → build/log_filter、build/optimized
make baseline        # → build/baseline
make test            # 公开测试 + 自建回归测试

# 方式四：src/ 工程布局（报告第 8 节的命令）
g++ -O2 -std=c++17 -pthread src/optimized.cpp -I src -o bench/optimized
g++ -O2 -std=c++17 -pthread bench/baseline.cpp -I src -o bench/baseline
```

编译口径统一为 **g++ 13.3.0 / `-O2 -std=c++17 -pthread`**。平台 checker 决定最终
编译器与资源限制；本包在这四种构建路径下的源码完全相同。

## 运行

```bash
# 现场生成数据（不需要任何数据集）
./build/log_filter --count 1000000 --hit-percent 50 --repeats 5

# 读固定文件
./build/log_filter --input data/n1m-r50.bin --output out/result.bin --repeats 5

# 对照实现（第一版的两遍分块方案，保留用于对比）
./build/log_filter --input data/n1m-r50.bin --impl twopass --threads 2 --repeats 5
```

输出中 `check=PASS` 表示结果已与平台参考实现逐条、逐字段、按顺序比对通过。

## 测试

```bash
# CMake 构建后（默认已注册测试）
ctest --test-dir build --output-on-failure

# 或直接对可执行文件运行
python3 tests/test_public.py    build/log_filter     # 平台公开测试，7 项
python3 tests/test_regression.py build/log_filter    # 自建回归测试，7 项
```

`tests/test_public.py` 与平台提供的文件逐字节相同（`cmp` 已验证）；公开测试的用法
示例就是 `python3 tests/test_public.py build/log_filter`。

## 复现实验

```bash
bash bench/verify.sh                              # 正确性全量复检（约 35 秒，缺数据集自动补建）
PERF_ASSUME_YES=1 bash bench/perf.sh 4 20         # 性能完整复现（约 10–15 分钟，需机器空闲）
bash bench/interleaved.sh data/n1m-r50.bin 20 6   # 逐样本交替（最可信判据，自动落盘）
python3 bench/analyze_interleaved.py results/interleaved-live.txt
```

> 数据集不随提交包分发（`data/`、`*.bin` 已被 `.gitignore` 排除）；上述脚本会按需补建。
> 详见 `REPORT.md` 第 8 节「复现入口」。

## 文档与证据

- [`REPORT.md`](REPORT.md) —— 完整实验报告（A4 排版，实现、假设、消融、退化场景、已知局限）
- [`REPORT-SUMMARY.md`](REPORT-SUMMARY.md) —— 精简版摘要
- [`report.pdf`](report.pdf) —— 完整报告的 PDF（可直接打印/评审）
- [`results/README.txt`](results/README.txt) —— 全部实验证据的索引

## 版本标签

`v0` 原始基线 → `v1` 两遍分块（正确但更慢）→ `v2` 单遍无分支定为默认 →
`v3` 测试与报告 → `v4` 规模扫描与图表 → `v4.1/v4.2` 归因更正 →
`v5` 交付合规修复 → `v5.1` 打包可复现 → `v5.2` 构建入口对齐平台约定
（根目录单源文件、默认产物 `build/log_filter`）
