#!/usr/bin/env bash
# ============================================================================
#  verify.sh —— 快速复现（约 30 秒 ~ 1 分钟）
#
#   内容：环境记录 → 构建两个二进制 → 核对输入/标准答案指纹 → 公开测试
#         → 自建回归测试 → 60 组参数化差分（single / twopass×1 / twopass×2）
#
#   用法：  bash bench/verify.sh
#   前置：  数据集已在 data/，标准答案已在 gold/（缺失时会自动用 baseline 生成）
#   产物：  results/verify-quick.txt（不改动 results/ 下已有的证据文件）
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")/.."

OUT=results/verify-quick.txt
exec > "$OUT" 2>&1          # 全量记录写文件；终端只打印末尾摘要（见脚本最后一步）

echo "##################### 0. 环境 #####################"
date -Is
echo "kernel : $(uname -srm)"
echo "cpu    : $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2- | xargs)"
echo "nproc  : $(nproc)"
echo "g++    : $(g++ --version | head -1)"
echo "python : $(python3 --version)"

echo
# 数据、标准答案与输出目录都不随包分发，先建好
mkdir -p data gold out results

echo "##################### 1. 构建 #####################"
echo "\$ g++ -O2 -std=c++17 -pthread bench/baseline.cpp -I src -o bench/baseline"
g++ -O2 -std=c++17 -pthread bench/baseline.cpp -I src -o bench/baseline
echo "\$ g++ -O2 -std=c++17 -pthread src/optimized.cpp  -I src -o bench/optimized"
g++ -O2 -std=c++17 -pthread src/optimized.cpp  -I src -o bench/optimized
ls -l bench/baseline bench/optimized

echo
echo "##################### 2. 输入指纹 #####################"
# 数据集不随提交包分发（规范要求）。若 data/ 为空，按三级回退补建（见 bench/gen_helper.sh）；
# 三条路径产出的文件逐字节相同，故 sha256 可直接与 results/input-sha256*.txt 核对。
source bench/gen_helper.sh
if [ -n "$HPC3_GEN" ]; then echo "补建数据将使用平台生成器: $HPC3_GEN"
else echo "未找到 generate_logs.py，补建数据将使用程序自带生成器（同算法同编码，产出逐字节相同）"; fi
gen_all_datasets
for f in n1m-r50 n1m-r0 n1m-r100 n2m-b90 n10m-r50; do
  printf '%s  %s\n' "$(sha256sum "data/$f.bin" | cut -c1-16)" "$f.bin"
done

echo
echo "##################### 3. 标准答案指纹 #####################"
for f in n1m-r50 n1m-r0 n1m-r100 n2m-b90 n10m-r50; do
  if [ ! -f "gold/$f.out" ]; then
    echo "生成 gold/$f.out（baseline，--repeats 1）"
    ./bench/baseline --input "data/$f.bin" --output "gold/$f.out" --repeats 1 | tail -1
  fi
  printf '%s  %s\n' "$(sha256sum "gold/$f.out" | cut -c1-16)" "$f.out"
done

echo
echo "##################### 4. 公开测试（未修改） #####################"
# 参照文件可能在上一级（开发工作区）或就在根目录（解包后的提交包）；都没有则跳过比对
if [ -f ../test_public.py ]; then
  if cmp -s tests/test_public.py ../test_public.py; then
    echo "✅ tests/test_public.py 与平台原始文件逐字节相同（参照: ../test_public.py）"
  else
    echo "❌ tests/test_public.py 已被改动！"
  fi
elif [ -f ./test_public.py ]; then
  if cmp -s tests/test_public.py ./test_public.py; then
    echo "✅ tests/test_public.py 与平台原始文件逐字节相同（参照: ./test_public.py）"
  else
    echo "❌ tests/test_public.py 已被改动！"
  fi
else
  echo "（未提供平台原始 test_public.py，跳过逐字节比对；不影响下面的测试运行）"
fi
python3 tests/test_public.py bench/optimized 2>&1 | tail -4

echo
echo "##################### 5. 自建回归测试 #####################"
python3 tests/test_regression.py bench/optimized 2>&1 | tail -4

echo
echo "##################### 6. 参数化差分（60 组） #####################"
python3 bench/diff_check.py --exe ./bench/optimized --base ./bench/baseline \
        2>&1 | tail -3

echo
echo "##################### 7. 输出逐字节比对 #####################"
for f in n1m-r50 n1m-r0 n1m-r100 n2m-b90 n10m-r50; do
  rm -f "out/$f.out"
  ./bench/optimized --input "data/$f.bin" --output "out/$f.out" --repeats 1 > /dev/null
  if cmp -s "out/$f.out" "gold/$f.out"; then echo "✅ $f  逐字节一致"; else echo "❌ $f  不一致"; fi
done

echo
echo "全部快速检查完成。原始记录: $OUT"

# 终端摘要（完整记录在 $OUT）
echo
echo "================ 摘要 ================"
grep -E '✅|❌|Ran [0-9]+ tests|^OK$|总计 [0-9]+ 次比对|^kernel|^cpu|^nproc|^g\+\+|^python' "$OUT" | tail -25
