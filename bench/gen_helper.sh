#!/usr/bin/env bash
# ============================================================================
#  gen_helper.sh —— 数据集补建工具（被 verify.sh / perf.sh 复用）
#
#  数据集不随提交包分发（平台规范），因此脚本在需要时会按三级回退补建：
#    ① ../generate_logs.py        平台原始生成器（开发工作区布局）
#    ② ./generate_logs.py         平台原始生成器（与包放在一起时）
#    ③ ./bench/optimized --export-input ...
#       程序自带同一生成算法与编解码（随机数发生器逐位相同），
#       实测导出文件与平台生成器产出**逐字节相同**（同一 sha256），
#       因此补建出的数据可直接与 results/input-sha256*.txt、manifest-*.json 核对。
#
#  用法: source bench/gen_helper.sh && gen_dataset 1000000 50 random data/n1m-r50.bin
# ============================================================================

HPC3_GEN=""
for _cand in ../generate_logs.py ./generate_logs.py; do
  [ -f "$_cand" ] && HPC3_GEN="$_cand" && break
done

gen_dataset() { # gen_dataset <count> <hit-percent> <pattern> <输出文件>
  local count="$1" hit="$2" pattern="$3" out="$4"
  if [ -f "$out" ]; then return 0; fi
  mkdir -p "$(dirname "$out")"      # 数据目录不在提交包内，需先建
  if [ -n "$HPC3_GEN" ]; then
    python3 "$HPC3_GEN" --count "$count" --hit-percent "$hit" --pattern "$pattern" \
            --seed 2026 --output "$out"
  else
    ./bench/optimized --count "$count" --hit-percent "$hit" --pattern "$pattern" \
                      --seed 2026 --export-input "$out" --repeats 1 > /dev/null
  fi
}

# 五个标准数据集（名称 → 参数），供脚本循环调用
gen_all_datasets() {
  gen_dataset 1000000  50 random data/n1m-r50.bin
  gen_dataset 1000000   0 random data/n1m-r0.bin
  gen_dataset 1000000 100 random data/n1m-r100.bin
  gen_dataset 2000000  90 blocks data/n2m-b90.bin
  gen_dataset 10000000 50 random data/n10m-r50.bin
}
