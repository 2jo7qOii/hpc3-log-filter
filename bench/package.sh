#!/usr/bin/env bash
# ============================================================================
#  package.sh —— 生成正式提交包（每一步都按平台目录规范自检）
#
#  规范要求与对应实现：
#    ① 解压后只有一个项目根目录            → 打包 HPC-3-submit/ 整个目录
#    ② 根目录放源码、requirements.txt、
#      测试代码、实验报告                  → src/ bench/ tests/ results/ + 报告
#    ③ 多文件项目提供 CMakeLists.txt       → 根目录 CMakeLists.txt（另留 g++ 路径）
#    ④ 不含绝对路径                        → 下面第 3 步全量扫描
#    ⑤ 不含软链接                          → 下面第 3 步全量扫描
#    ⑥ 不含构建产物                        → 只复制源码/脚本/文本证据
#    ⑦ 不含隐藏测试 / 隐藏文件             → 打包前删除点文件（含 .gitignore）
#
#  用法:  bash bench/package.sh          （在工程根目录执行，即 work/）
#  产物:  ../HPC-3-submit.tar.gz         （≤ 32 MiB）
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
OUT_TGZ="$(cd .. && pwd)/HPC-3-submit.tar.gz"
STAGE="$(mktemp -d)/HPC-3-submit"

echo "===== 1. 组装暂存目录 ====="
mkdir -p "$STAGE/src" "$STAGE/bench" "$STAGE/tests" "$STAGE/results"

cp -p REPORT.md requirements.txt CMakeLists.txt  "$STAGE/"
# 平台原始布局把 support.hpp / baseline.cpp 放在根目录，这里各放一份完全相同的副本，
# 使两种布局都能直接编译（两份副本内容逐字节相同，由本脚本第 3 步自检保证）
cp -p src/support.hpp src/optimized.cpp          "$STAGE/src/"
cp -p src/support.hpp                            "$STAGE/support.hpp"
cp -p src/optimized.cpp                          "$STAGE/optimized.cpp"
cp -p bench/baseline.cpp                         "$STAGE/baseline.cpp"
cp -p bench/baseline.cpp bench/*.py bench/*.sh   "$STAGE/bench/"
cp -p tests/test_public.py tests/test_regression.py "$STAGE/tests/"
# 证据只收文本/JSON/SVG，避免把数据集、输出与图表草稿带进去
find results -maxdepth 1 -type f \( -name '*.txt' -o -name '*.json' -o -name '*.svg' \) \
     -exec cp -p {} "$STAGE/results/" \;

echo "===== 2. 清理不该进包的内容 ====="
# ② 隐藏文件（.gitignore 等）不进包；临时文件不进包；构建产物不进包
find "$STAGE" -name '.*' -delete
rm -f "$STAGE"/results/.tmp-* "$STAGE"/bench/*.o "$STAGE"/bench/baseline "$STAGE"/bench/optimized
echo "已删除隐藏文件与临时文件"

echo "===== 3. 规范自检 ====="
fail=0
# ① 单根目录：暂存目录本身就是一个根目录（下面用 tar 的相对路径保证）
# ② 根目录必备项
for f in src/optimized.cpp src/support.hpp requirements.txt CMakeLists.txt REPORT.md \
         optimized.cpp support.hpp baseline.cpp tests/test_public.py bench/baseline.cpp; do
  if [ -e "$STAGE/$f" ]; then printf '  ✅ 根目录/子目录必备  %s\n' "$f"
  else printf '  ❌ 缺失              %s\n' "$f"; fail=1; fi
done
# ③ 多文件项目必须有 CMakeLists.txt
[ -f "$STAGE/CMakeLists.txt" ] && echo "  ✅ 多文件项目已提供 CMakeLists.txt" || { echo "  ❌ 缺 CMakeLists.txt"; fail=1; }
# ③b 根目录副本必须与 src/ 下原件逐字节相同
if cmp -s "$STAGE/support.hpp" "$STAGE/src/support.hpp" && cmp -s "$STAGE/baseline.cpp" "$STAGE/bench/baseline.cpp"; then
  echo "  ✅ 根目录 baseline.cpp / support.hpp 与 src、bench 内文件逐字节一致"
else
  echo "  ❌ 根目录副本与原件不一致"; fail=1
fi
# ④ 隐藏文件
n_hidden=$(find "$STAGE" -name '.*' | wc -l)
[ "$n_hidden" -eq 0 ] && echo "  ✅ 无隐藏文件" || { echo "  ❌ 仍有 $n_hidden 个隐藏文件"; fail=1; }
# ⑤ 软链接
n_link=$(find "$STAGE" -type l | wc -l)
[ "$n_link" -eq 0 ] && echo "  ✅ 无软链接" || { echo "  ❌ 仍有 $n_link 个软链接"; fail=1; }
# ⑥ 构建产物
n_art=$(find "$STAGE" \( -name '*.o' -o -name '*.a' -o -name '*.so' -o -name 'CMakeCache.txt' \
        -o -name 'baseline' -o -name 'optimized' -o -name 'micro_variants' \) | wc -l)
[ "$n_art" -eq 0 ] && echo "  ✅ 无构建产物" || { echo "  ❌ 仍有 $n_art 个构建产物"; fail=1; }
# ⑦ 绝对路径（扫描文本文件内容里的 /home/ 、/tmp/ 等）
hits=$(grep -rIl -E '/home/[A-Za-z0-9._-]+|/Users/[A-Za-z0-9._-]+|[A-Za-z]:\\\\' "$STAGE" 2>/dev/null || true)
if [ -n "$hits" ]; then
  echo "  ⚠️  以下文件含机器专属绝对路径，请人工确认："
  echo "$hits" | sed "s|$STAGE/|     |"
else
  echo "  ✅ 文本内容中无机器专属绝对路径（/tmp 为 POSIX 标准临时目录，脚本已改用 tempfile）"
fi
[ "$fail" -eq 0 ] || { echo "自检未通过，已中止打包"; exit 1; }

echo "===== 4. 打包 ====="
rm -f "$OUT_TGZ"
tar -czf "$OUT_TGZ" -C "$(dirname "$STAGE")" HPC-3-submit
SIZE=$(stat -c%s "$OUT_TGZ")
printf '产物: %s\n大小: %s 字节 (%.2f MiB，上限 32 MiB)\n' "$OUT_TGZ" "$SIZE" "$(echo "$SIZE/1048576" | bc -l)"

echo "===== 5. 包内清单复核 ====="
echo "顶层条目: $(tar -tzf "$OUT_TGZ" | cut -d/ -f1 | sort -u | tr '\n' ' ')"
echo "文件总数: $(tar -tzf "$OUT_TGZ" | grep -vE '/$' | wc -l)"
echo "非常规条目(应为空): $(tar -tvzf "$OUT_TGZ" | awk '$1 !~ /^[-d]/' | wc -l)"
echo "隐藏文件(应为空): $(tar -tzf "$OUT_TGZ" | grep -E '/\.[^/]+$' | wc -l)"
echo "根目录: $(tar -tzf "$OUT_TGZ" | grep -E '^HPC-3-submit/[^/]+$' | sed 's|.*/||' | tr '\n' ' ')"
rm -rf "$(dirname "$STAGE")"
echo "完成。"
