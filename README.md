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

## 构建

```bash
# 方式一：CMake
cmake -S . -B build && cmake --build build      # → build/optimized、build/baseline

# 方式二：g++
g++ -O2 -std=c++17 -pthread src/optimized.cpp  -I src -o bench/optimized
g++ -O2 -std=c++17 -pthread bench/baseline.cpp -I src -o bench/baseline
```

## 运行

```bash
# 现场生成数据（不需要任何数据集）
./bench/optimized --count 1000000 --hit-percent 50 --repeats 5

# 读固定文件
./bench/optimized --input data/n1m-r50.bin --output out/result.bin --repeats 5

# 对照实现（第一版的两遍分块方案，保留用于对比）
./bench/optimized --input data/n1m-r50.bin --impl twopass --threads 2 --repeats 5
```

输出中 `check=PASS` 表示结果已与平台参考实现逐条、逐字段、按顺序比对通过。

## 复现实验

```bash
bash bench/verify.sh                              # 正确性全量复检（约 35 秒，缺数据集自动补建）
PERF_ASSUME_YES=1 bash bench/perf.sh 4 20         # 性能完整复现（约 10–15 分钟，需机器空闲）
bash bench/interleaved.sh data/n1m-r50.bin 20 6   # 逐样本交替（最可信判据，自动落盘）
python3 bench/analyze_interleaved.py results/interleaved-live.txt
```

> 数据集不随仓库分发（`data/`、`*.bin` 已被 `.gitignore` 排除）；上述脚本会按需补建。
> 详见 `REPORT.md` 第 8 节「复现入口」。

## 文档与证据

- [`REPORT.md`](REPORT.md) —— 完整实验报告（实现、假设、消融、退化场景、已知局限）
- [`REPORT-SUMMARY.md`](REPORT-SUMMARY.md) —— 精简版摘要
- [`results/README.txt`](results/README.txt) —— 全部实验证据的索引

## 目录

| 路径 | 内容 |
|---|---|
| `src/` | 实现（`optimized.cpp`）+ 平台提供的 `support.hpp` |
| `bench/` | 原始基线、复现脚本、消融微基准、统计与打包工具 |
| `tests/` | 公开测试（平台原文件，逐字节未改）+ 自建回归测试 |
| `results/` | 原始样本、输入/输出指纹、图表、复现记录 |

## 版本标签

`v0` 原始基线 → `v1` 两遍分块（正确但更慢）→ `v2` 单遍无分支定为默认 →
`v3` 测试与报告 → `v4` 规模扫描与图表 → `v4.1/v4.2` 归因更正 →
`v5` 交付合规修复 → `v5.1` 打包可复现
