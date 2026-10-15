#!/usr/bin/env bash
# 交替重复测量 + 统计最好/中位。A=baseline, B=optimized。
# 用法: bash bench/bench_run.sh <输入文件> <轮数> [传给程序的额外参数...]
set -u
IN="$1"; ROUNDS="$2"; shift 2
echo "##### 输入: $(basename "$IN")  轮数: $ROUNDS  附加参数: ${*:-（无）} #####"
echo "##### sha256: $(sha256sum "$IN" | cut -d' ' -f1) #####"
for r in $(seq 1 "$ROUNDS"); do
  for tag in A B; do
    if [ "$tag" = A ]; then BIN=./bench/baseline; else BIN=./bench/optimized; fi
    raw=$($BIN --input "$IN" --repeats 5 "$@" 2>/dev/null)
    samples=$(printf '%s\n' "$raw" | grep -oP 'core_ms=\K[0-9.]+')
    med=$(printf '%s\n' "$raw" | grep -oP '^median_core_ms=\K[0-9.]+')
    best=$(printf '%s\n' "$samples" | sort -g | head -1)
    printf 'round=%d impl=%s best=%-10s median=%-10s samples=[ %s]\n' \
           "$r" "$tag" "$best" "$med" "$(printf '%s ' $samples)"
  done
done
