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
ab-1m-r0.txt               性能实验：1M hit0（边界）
ab-1m-r100.txt             性能实验：1M hit100（边界）
exp-threads-10m.txt        线程扩展性实验（twopass 1/2/4 线程 vs single）
exp-1m.txt                 早期 1M 多实现对比
baseline-1m-file.txt       基线单独一次 5 样本记录
scale-sweep.txt            统一会话规模扫描（10 万 ~ 1000 万条，A/B 交替重复）

chart-scale.svg            规模扫描图表（耗时 + 加速比）
chart-hitrate.svg          命中率扫描图表（耗时 + 加速比）
                           由 bench/make_charts.py 生成（无第三方依赖）

说明：本目录只放可复核的原始记录，不存放数据集与输出文件（见 ../.gitignore）。
