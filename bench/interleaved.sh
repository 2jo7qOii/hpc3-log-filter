#!/usr/bin/env bash
# ============================================================================
#  interleaved.sh —— 逐样本交替 A/B 测量（最可信的判据）
#
#  A = bench/baseline，B = bench/optimized。每个样本点一个独立进程（与题目计时口径
#  一致：core 只含一次 filter_records）；轮内 A/B 相邻、偶数轮反转先后顺序，
#  因此 A、B 共享同一热轨迹，可用配对统计判断差异是否真实。
#
#  用法: bash bench/interleaved.sh <input.bin> [轮数] [每轮样本数] [输出文件]
#        输出文件默认 results/interleaved-live.txt（同时也打印到终端）。
#
#  分析:
#    python3 bench/analyze_interleaved.py <输出文件>   # 只分析本次测量（推荐）
#    python3 bench/analyze_interleaved.py              # 分析 results/ 下全部
#                                                      # interleaved-*.txt（含归档旧样本）
#
#  实现注意：输出用**同步管道** `{ ... } | tee` 落盘。不能用
#  `exec > >(tee "$OUT")` —— 进程替换是异步的，tee 的写入会与终端输出交错，
#  导致标题行被拆散、分析脚本解析不出 input= 而把段名显示为 "?"（实测踩到过）。
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")/.."

IN="$1"; ROUNDS="${2:-10}"; PER="${3:-6}"
OUT="${4:-results/interleaved-live.txt}"

# 前置检查：数据集不随包分发，缺失时必须**立即退出**并给出可执行的补救命令，
# 否则会跑满全部轮次、每轮都只打印 "error: cannot open input"，最后产出空文件（已踩到）。
if [ ! -f "$IN" ]; then
  cat >&2 <<EOF
错误：输入文件不存在 —— $IN

数据集不随提交包分发，需要先补建。任选一种：
  (a) 补建全部数据集并做正确性复检（推荐，约 35 秒）:
        bash bench/verify.sh
  (b) 只生成这一份 1M 数据集:
        mkdir -p data
        ./bench/optimized --count 1000000 --hit-percent 50 --pattern random --seed 2026 --export-input data/n1m-r50.bin --repeats 1 > /dev/null
补建后可核对 sha256（1M random/50 应为 d11bc48ae929db3f…）。
EOF
  exit 2
fi

mkdir -p "$(dirname "$OUT")"

{
  echo "### 逐样本交替 A/B  (input=$IN rounds=$ROUNDS samples/round=$PER)"
  echo "### 采集时间: $(date -Is)"
  echo "### A=baseline  B=optimized（默认 single）；轮内相邻、偶数轮反转先后"
  for r in $(seq 1 "$ROUNDS"); do
    sa=(); sb=()
    for k in $(seq 1 "$PER"); do
      if [ $((r % 2)) -eq 0 ]; then order="B A"; else order="A B"; fi
      for impl in $order; do
        if [ "$impl" = A ]; then bin=./bench/baseline; else bin=./bench/optimized; fi
        v=$("$bin" --input "$IN" --repeats 1 | sed -n 's/^sample=0 core_ms=\([0-9.]*\).*/\1/p')
        if [ "$impl" = A ]; then sa+=("$v"); else sb+=("$v"); fi
      done
    done
    echo "round=$r A=[${sa[*]}] B=[${sb[*]}]"
  done
  echo
  echo "### 以上为本次测量的全部原始样本，已写入: $OUT"
} 2>&1 | tee "$OUT"

echo
echo "下一步（只分析本次测量，不含归档旧样本）:"
echo "  python3 bench/analyze_interleaved.py $OUT"
