results/ —— 实验证据归档（全部为文本，随源码一起提交）
============================================================================

environment.txt            机器、编译器、Python、基线样本的环境记录
input-sha256*.txt          输入数据集的 sha256（输入指纹）
gold-sha256*.txt           标准答案输出的 sha256（输出指纹）
manifest-*.json            各数据集的生成参数清单（含 hitCountActual 等）
input-manifest.json        1M 数据集的生成清单

public-test-baseline.txt   公开测试结果（原始基线）
public-test-optimized.txt  公开测试结果（优化实现）
regression.txt             自建回归测试结果
diff-check.txt             参数化差分验证结果（60 次比对）
fingerprint-check.txt      5 个数据集输出与标准答案的逐字节比对结果

ab-1m-r50.txt              性能实验：1M random hit50（A/B 交替重复原始样本）
ab-2m-b90.txt              性能实验：2M blocks hit90（退化场景）
ab-10m-r50.txt             性能实验：10M random hit50
ab-1m-r0.txt               性能实验：1M hit0（边界）      [第四轮补齐：顺序口径 A/B，3 轮]
ab-1m-r100.txt             性能实验：1M hit100（边界）    [第四轮补齐：顺序口径 A/B，3 轮]
ab-v1-vs-v2.txt            两版实现并排复现：v1(两遍) vs v2(单遍无分支)，逐样本交替
exp-threads-10m.txt        线程扩展性实验（twopass 1/2/4 线程 vs single）
exp-1m.txt                 早期 1M 多实现对比
baseline-1m-file.txt       基线单独一次 5 样本记录
scale-sweep.txt            统一会话规模扫描（10 万 ~ 1000 万条，A/B 交替重复）

chart-scale.svg            规模扫描图表（耗时 + 加速比）
chart-hitrate.svg          命中率扫描图表（耗时 + 加速比）
                           由 bench/make_charts.py 生成（无第三方依赖）

说明：本目录只放可复核的原始记录，不存放数据集与输出文件（见 ../.gitignore）。

---- 第三轮（独立复测与归因更正）新增证据 ----
interleaved-ab.txt          逐样本交替 A/B 原始样本（1M/10M/0%/100%/blocks 五组）
                            方法：每样本点独立进程；轮内 A→B、偶数轮反转顺序
ablation-micro.txt          消融微基准原始样本（5 变体 × 4 个数据集）
                            变体 1=baseline 2=+阈值局部化 3=谓词按位与 4=+无条件写 5=等价写法
twopass-vs-single-10m.txt   空闲机重测：twopass 1/2/4 线程 vs single（10M）
ab-live/                    第三轮全套复现输出（含统计汇总与 JSON）
                            由 PERF_ASSUME_YES=1 bash bench/perf.sh 生成
verify-quick.txt            第三轮快检查记录（构建/指纹/公开测试/回归/差分/逐字节比对）

第四轮更正要点（详见 REPORT.md 5.4、5.5、8 节）：
  * 输入来源（--count vs --input）：速度无系统性差异，仍用 --input 是因可归档可核对；
  * 并行扩展性：twopass 2 线程可达 1.98×（接近线性），原"并行收益被吃掉"的解释作废；
    单遍仍快 1.86×，原因是"多读一遍输入 + 每次调用的线程创建/前缀和分配"这类固定成本；
  * 报告新增第 8 节"复现入口"，全部命令均已从解包后的提交包实测通过。

第三轮结论要点（详见 REPORT.md 第 7 节）：
  * 加速比可复现区间 1.7×~2.1×（原报告 2.52× 含"顺序 A/B + 取最小值"两个偏乐观因素）；
  * 收益来源更正为"消除数据相关的写出分支"（贡献 >95%），谓词改写与阈值局部化≈0；
  * 3.4 候选二/候选五的结论由"实测否定"降级为"未验证"（原始样本缺失）。

---- 可复现入口（第三轮新增工具）----
bench/verify.sh             快检查：构建+指纹+公开测试+回归+60 组差分+逐字节比对（约 35 秒）
bench/perf.sh               完整性能复现：规模扫描+交替 A/B+消融微基准+统计汇总（约 10 分钟）
bench/interleaved.sh        逐样本交替 A/B 测量（单数据集）
bench/micro_variants.cpp    消融微基准（5 变体）；配合 bench/micro_core.cpp 编译
bench/analyze_versions.py   规模扫描统计（min/分位/CV/bootstrap 置信区间）
bench/analyze_interleaved.py 交替样本配对统计（逐轮符号检验 + bootstrap 区间）
                            用法：`... analyze_interleaved.py <文件>` 只分析指定文件（推荐）；
                            不带参数则分析 results/ 下全部 interleaved-*.txt（含归档旧样本）。
                            输出会逐段标注 [来源: 文件路径]，避免把归档旧样本误当成本次测量。
bench/interleaved.sh        逐样本交替 A/B 测量；结果默认落盘 results/interleaved-live.txt
                            （第四轮修正：原先只打印终端、不落盘，导致下一步分析读到的是
                             仓库里的归档旧样本，容易误判）
bench/analyze_data_structure.py 输入数据的谓词通过率/游程/可预测性分析

---- 第四轮补齐：命中率两端证据 + 图表可交叉校验 ----
interleaved-extremes.txt        逐样本交替 A/B 原始样本（0% / 100% / blocks 90%）
interleaved-extremes-summary.txt 上述样本的配对统计与结论（本文件补充说明）
bench/charts_from_data.py       从原始样本直接重画图表（chart-*-data.svg）
perf-full-run-verification.txt 第四轮完整流程验证：从提交包跑通 perf.sh 六步
                                （含消融微基准与线程扩展性；数值与报告区间核对）
source-generated-vs-file.txt    输入来源对比：--count 现场生成 vs --input 固定文件
                                （逐样本交替 8 轮 × 3 样本；结论：无系统性差异，见 5.4）
vectorization-report.txt        向量化证据：编译器 -fopt-info-vec-* 诊断 + 反汇编 +
                                手工 AVX2 原型的结论（对应 REPORT.md 第 3.6 节）

背景：命中率图中「0%」与「100%」两点的数值原先只内嵌在 bench/make_charts.py 里，
      仓库内没有对应原始样本。现已用 bench/bench_run.sh 按同一口径补齐：
        bash bench/bench_run.sh data/n1m-r0.bin   3 | tee results/ab-1m-r0.txt
        bash bench/bench_run.sh data/n1m-r100.bin 3 | tee results/ab-1m-r100.txt
      实测（跨轮最小值）：0%  为 8.594 / 2.979 = 2.89×；100% 为 4.007 / 4.206 = 0.95×。
      与交替口径的配对统计（2.02× / 0.94×）方向一致，量级差异来自"取跨轮最小值"。

两种出图方式互为交叉校验（数值不一致即说明样本被替换或内嵌值被手改）：
  bench/make_charts.py            数值内嵌，保证交付图表逐字节可复现 → chart-*.svg
  bench/charts_from_data.py       数值现读原始样本，保证"重跑→出图"闭环 → chart-*-data.svg
  两者对照结果：规模扫描 6 个点完全一致；命中率图中 50% 点两来源不同
  （图表内嵌 7.85/3.79=2.07× 取自规模扫描，而 ab-1m-r50.txt 为 14.813/8.167=1.81×，
   图注已注明该点与规模扫描同源）。
