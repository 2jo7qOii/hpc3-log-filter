#!/usr/bin/env bash
# 独立复测：A(baseline) / B(optimized) 逐样本交替，消除热漂移与顺序偏差。
# 每个样本点必须是独立进程（与题目的计时口径一致：core 只含 filter_records）。
# 用法: bash bench/interleaved.sh <input.bin> <rounds> <samples_per_round>
set -euo pipefail
cd "$(dirname "$0")/.."

IN="$1"; ROUNDS="${2:-10}"; PER="${3:-6}"
echo "### 逐样本交替 A/B  (input=$IN rounds=$ROUNDS samples/round=$PER)"
echo "### 采集时间: $(date -Is)"
for r in $(seq 1 "$ROUNDS"); do
  sa=(); sb=()
  for k in $(seq 1 "$PER"); do
    # 顺序每轮反转，进一步抵消"谁先跑"的系统差异
    if [ $((r % 2)) -eq 0 ]; then order="B A"; else order="A B"; fi
    for impl in $order; do
      if [ "$impl" = A ]; then bin=./bench/baseline; else bin=./bench/optimized; fi
      v=$("$bin" --input "$IN" --repeats 1 | sed -n 's/^sample=0 core_ms=\([0-9.]*\).*/\1/p')
      if [ "$impl" = A ]; then sa+=("$v"); else sb+=("$v"); fi
    done
  done
  echo "round=$r A=[${sa[*]}] B=[${sb[*]}]"
done
