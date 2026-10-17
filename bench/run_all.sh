#!/usr/bin/env bash
# ============================================================================
#  一键复现全部正确性验证与性能实验
#
#  用法:  bash bench/run_all.sh          （在工程根目录执行）
#
#  前置：需要先由 generate_logs.py 生成输入数据（见 requirements.txt）；
#        若 data/ 下缺少数据，本脚本会调用平台的 generate_logs.py 生成。
#  产物：results/ 下的 *_public.txt / ab-*.txt / exp-*.txt（报告引用的原始样本）
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p data gold out results

echo "===== 1. 编译 ====="
g++ -O2 -std=c++17 -pthread bench/baseline.cpp  -I src -o bench/baseline
g++ -O2 -std=c++17 -pthread src/optimized.cpp   -I src -o bench/optimized

echo "===== 2. 生成/确认输入数据 ====="
# 数据集不随包分发。三级回退补建见 bench/gen_helper.sh：
#   平台 generate_logs.py → 包内同级副本 → 程序自带生成器（产出逐字节相同）
source bench/gen_helper.sh
[[ -n "$HPC3_GEN" ]] && echo "使用平台生成器: $HPC3_GEN" || echo "未找到 generate_logs.py，使用程序自带生成器（同算法，产出逐字节相同）"
gen_all_datasets

echo "===== 3. 生成标准答案（baseline 输出，作为输出指纹）====="
for f in n1m-r50 n1m-r0 n1m-r100 n2m-b90 n10m-r50; do
  if [ ! -f "gold/$f.out" ]; then
    ./bench/baseline --input "data/$f.bin" --output "gold/$f.out" --repeats 1 | tail -1
  fi
  sha256sum "data/$f.bin" >> results/input-sha256-all.txt
  sha256sum "gold/$f.out" >> results/gold-sha256-all.txt
done

echo "===== 4. 公开测试（原始基线 + 优化实现）====="
{ echo "### 公开测试 —— 优化实现"; python3 tests/test_public.py bench/optimized; } \
  2>&1 | tee results/public-test-optimized.txt | tail -3

echo "===== 5. 回归测试 ====="
python3 tests/test_regression.py bench/optimized 2>&1 | tee results/regression.txt | tail -3

echo "===== 6. 差分验证（多参数 × 多实现）====="
python3 bench/diff_check.py --exe ./bench/optimized --base ./bench/baseline \
        2>&1 | tee results/diff-check.txt | tail -2

echo "===== 7. 输出指纹比对（优化实现 vs 标准答案）====="
for f in n1m-r50 n1m-r0 n1m-r100 n2m-b90 n10m-r50; do
  rm -f "out/$f.out"
  ./bench/optimized --input "data/$f.bin" --output "out/$f.out" --repeats 1 > /dev/null
  if cmp -s "out/$f.out" "gold/$f.out"; then echo "✅ $f 逐字节一致"; else echo "❌ $f 不一致"; fi
done | tee results/fingerprint-check.txt

echo "===== 8. 性能实验（交替重复，A=baseline B=optimized）====="
bash bench/bench_run.sh data/n1m-r50.bin  3 | tee results/ab-1m-r50.txt
bash bench/bench_run.sh data/n2m-b90.bin  4 | tee results/ab-2m-b90.txt
bash bench/bench_run.sh data/n10m-r50.bin 5 | tee results/ab-10m-r50.txt
bash bench/bench_run.sh data/n1m-r0.bin   2 | tee results/ab-1m-r0.txt
bash bench/bench_run.sh data/n1m-r100.bin 2 | tee results/ab-1m-r100.txt

echo "===== 8b. 规模扫描（命中率 50%）====="
gen 100000   50 random n100000-r50.bin
gen 250000   50 random n250000-r50.bin
gen 500000   50 random n500000-r50.bin
gen 2000000  50 random n2000000-r50.bin
{
  echo "############ 统一会话规模扫描 ############"
  echo "口径：--input 固定文件；A=baseline B=optimized；每轮各 5 次取跨轮最小值"
  echo "采集时间: $(date -Is)"
  echo
  for f in n100000-r50 n250000-r50 n500000-r50 n1m-r50 n2000000-r50 n10m-r50; do
    [ -f "data/$f.bin" ] || continue
    [ -f "gold/$f.out" ] || ./bench/baseline --input "data/$f.bin" --output "gold/$f.out" --repeats 1 > /dev/null
    echo "===== $f  ($(stat -c%s data/$f.bin) 字节) ====="
    bash bench/bench_run.sh "data/$f.bin" 4 2>&1 | grep -E 'round='
    echo
  done
} > results/scale-sweep.txt 2>&1
echo "规模扫描完成 -> results/scale-sweep.txt"

echo "===== 8c. 生成图表 ====="
python3 bench/make_charts.py

echo "===== 9. 线程扩展性（10M）====="
{ for t in 1 2 4; do
    echo "--- twopass --threads $t ---"
    ./bench/optimized --input data/n10m-r50.bin --repeats 5 --impl twopass --threads "$t" | grep -E '^sample=|^median_core'
  done
  echo "--- single ---"
  ./bench/optimized --input data/n10m-r50.bin --repeats 5 --impl single | grep -E '^sample=|^median_core'
} 2>&1 | tee results/exp-threads-10m.txt

echo
echo "全部完成。原始样本见 results/ 目录。"
