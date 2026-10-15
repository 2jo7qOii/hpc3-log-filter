#!/usr/bin/env bash
# ============================================================================
#  perf.sh —— 完整性能复现（约 8 ~ 12 分钟，含 10M 数据）
#
#   内容：
#     1. 规模扫描（A=baseline / B=optimized，顺序执行，与原 results/ 同口径）
#     2. 逐样本交替 A/B（消除"先跑完全部 A 再跑全部 B"的顺序/热漂移偏差）
#     3. 命中率两端（0% / 100%）与退化场景（blocks 90%）
#     4. 消融微基准：把"无分支搬运"拆成 5 个变体单独计时
#     5. 数据可预测性分析（谓词通过率 / 游程 / 理论错预测下界）
#     6. 统计汇总（最小值、中位数、bootstrap 置信区间、配对符号检验）
#
#   用法：  bash bench/perf.sh [规模扫描轮数] [交替测量轮数]
#   产物：  全部写入 results/ab-live/  —— 不覆盖 results/ 下已有的证据文件
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")/.."

LIVE=results/ab-live
mkdir -p "$LIVE"

SCALE_ROUNDS="${1:-4}"
INTER_ROUNDS="${2:-20}"

# ---- 前置检查：机器必须空闲，否则测量无意义 ----
LOAD1=$(awk '{print $1}' /proc/loadavg)
BUSY=$(pgrep -c -f 'bench/(baseline|optimized)|micro_variants|interleaved.sh' 2>/dev/null || true)
echo "### 前置检查：load1=$LOAD1  并发测量进程=${BUSY:-0}"
if [ "${BUSY:-0}" -gt 0 ]; then
  echo "!! 检测到别的测量进程正在运行，会让本次数字失真。请先结束它们再跑。" >&2
  exit 3
fi
if awk "BEGIN{exit !($LOAD1 > 1.0)}"; then
  echo "!! 当前 1 分钟负载 $LOAD1 > 1.0，机器不空闲。" >&2
  echo "   建议等负载降到 1 以下（uptime 查看）再跑，否则加速比不可信。" >&2
  if [ "${PERF_ASSUME_YES:-0}" = "1" ]; then
    echo "   PERF_ASSUME_YES=1：继续。" >&2
  else
    read -r -p "   仍要继续？(y/N) " ans </dev/tty || ans=n; [ "$ans" = y ] || exit 3
  fi
fi

echo "##################### 0. 构建 #####################"
g++ -O2 -std=c++17 -pthread bench/baseline.cpp -I src -o bench/baseline
g++ -O2 -std=c++17 -pthread src/optimized.cpp  -I src -o bench/optimized
# 微基准需要多一个翻译单元；-mclflushopt 用于把输入刷出缓存
g++ -O2 -std=c++17 -pthread -mclflushopt -march=x86-64 \
    bench/micro_variants.cpp bench/micro_core.cpp -I src -o bench/micro_variants
echo "构建完成: bench/baseline  bench/optimized  bench/micro_variants"

echo
echo "##################### 1. 规模扫描（顺序 A/B，--input 固定文件） #####################"
{
  echo "############ 统一会话规模扫描（A/B 各一轮，每轮 5 次）############"
  echo "口径：--input 固定文件；A=baseline B=optimized；每轮 5 次，取跨轮最小值"
  echo "采集时间: $(date -Is)"
  echo
  for f in n100000-r50 n250000-r50 n500000-r50 n1m-r50 n2000000-r50 n10m-r50; do
    if [ ! -f "data/$f.bin" ]; then
      case $f in
        n100000-r50)  python3 ../generate_logs.py --count 100000   --hit-percent 50 --pattern random --seed 2026 --output data/$f.bin ;;
        n250000-r50)  python3 ../generate_logs.py --count 250000   --hit-percent 50 --pattern random --seed 2026 --output data/$f.bin ;;
        n500000-r50)  python3 ../generate_logs.py --count 500000   --hit-percent 50 --pattern random --seed 2026 --output data/$f.bin ;;
        n2000000-r50) python3 ../generate_logs.py --count 2000000  --hit-percent 50 --pattern random --seed 2026 --output data/$f.bin ;;
      esac
    fi
    [ -f "gold/$f.out" ] || ./bench/baseline --input "data/$f.bin" --output "gold/$f.out" --repeats 1 > /dev/null
    echo "===== $f  ($(stat -c%s "data/$f.bin") 字节) ====="
    bash bench/bench_run.sh "data/$f.bin" "$SCALE_ROUNDS" 2>&1 | grep -E 'round='
    echo
  done
} > "$LIVE/scale-sweep.txt" 2>&1
echo "-> $LIVE/scale-sweep.txt"

echo
echo "##################### 2. 逐样本交替 A/B #####################"
bash bench/interleaved.sh data/n1m-r50.bin  "$INTER_ROUNDS" 6 | tee "$LIVE/interleaved-n1m.txt"
echo
bash bench/interleaved.sh data/n10m-r50.bin 8 4              | tee "$LIVE/interleaved-n10m.txt"

echo
echo "##################### 3. 退化 / 边界场景 #####################"
for spec in "n2m-b90 4" "n1m-r0 3" "n1m-r100 3"; do
  set -- $spec
  bash bench/bench_run.sh "data/$1.bin" "$2" | tee "$LIVE/ab-$1.txt"
  echo
done

echo
echo "##################### 4. 消融微基准（5 个变体） #####################"
{
  echo "########## 1M random hit50 ##########"; ./bench/micro_variants data/n1m-r50.bin   14
  echo; echo "########## 2M blocks hit90 ##########"; ./bench/micro_variants data/n2m-b90.bin    14
  echo; echo "########## 1M random hit0 ##########";  ./bench/micro_variants data/n1m-r0.bin     10
  echo; echo "########## 1M random hit100 ##########";./bench/micro_variants data/n1m-r100.bin   10
} > "$LIVE/micro-variants.txt" 2>&1
grep -E '^(变体|### check|1_|2_|3_|4_|5_)' "$LIVE/micro-variants.txt" | grep -v PASS | head -30

echo
echo "##################### 5. 数据可预测性分析 #####################"
python3 bench/analyze_data_structure.py | tee "$LIVE/data-structure.txt" | grep -E '===|谓词通过率|游程'

echo
echo "##################### 6. 统计汇总 #####################"
ANALYSIS_DIR="$LIVE" python3 bench/analyze_versions.py 2>&1 | tee "$LIVE/analysis-sweep.txt" | tail -30 || true
ANALYSIS_DIR="$LIVE" python3 bench/analyze_interleaved.py 2>&1 | tee "$LIVE/analysis-interleaved.txt" | grep -E "data/|中位=|加速比|符号检验" || true

echo
echo "全部性能实验完成。原始记录在 $LIVE/ 下："
ls -l "$LIVE"
