#!/usr/bin/env python3
"""离线分析输入数据里"命中的可预测性" —— 直接解释 baseline 分支代价的来源。

只读 data/*.bin，输出：
  * 各谓词的单独通过率与联合命中率
  * 命中序列的游程长度分布（长游程 = 分支好预测）
  * 用 2 位饱和计数器（gshare 风格的简化模型）模拟 baseline 那 4 个分支的
    错预测率，以及"块结构"与"随机结构"的差别
"""
import pathlib, struct, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
REC = struct.Struct("<QIIII")   # timestamp, source_id, latency_us, payload_bytes, flags

QUERY = dict(begin=1000, end=2000, lat=100, flags=3)


def records(path, limit=None):
    with open(path, "rb") as f:
        head = f.read(24)
        assert head[:8] == b"NCULOG01", head[:8]
        n = struct.unpack_from("<Q", head, 16)[0]
        if limit:
            n = min(n, limit)
        buf = f.read(24 * n)
    for i in range(n):
        yield REC.unpack_from(buf, 24 * i)


def run_lengths(seq):
    if not seq:
        return []
    runs, cur = [], 1
    for i in range(1, len(seq)):
        if seq[i] == seq[i - 1]:
            cur += 1
        else:
            runs.append(cur)
            cur = 1
    runs.append(cur)
    return runs


def analyse(name, path, limit=None):
    hits, ts_ok, lat_ok, fl_ok = [], [], [], []
    n = 0
    for (t, sid, lat, pay, fl) in records(path, limit):
        a = QUERY["begin"] <= t < QUERY["end"]
        b = lat >= QUERY["lat"]
        c = (fl & QUERY["flags"]) == QUERY["flags"]
        ts_ok.append(a); lat_ok.append(b); fl_ok.append(c)
        hits.append(a and b and c)
        n += 1
    rl = run_lengths(hits)
    ones = sum(hits)
    print(f"\n=== {name}  n={n:,} ===")
    print(f"  谓词通过率: 时间戳 {sum(ts_ok)/n:7.2%}  延迟 {sum(lat_ok)/n:7.2%}  "
          f"flags {sum(fl_ok)/n:7.2%}  联合命中 {ones/n:7.4%}")
    if rl:
        print(f"  命中序列游程: 条数={len(rl):,}  平均={sum(rl)/len(rl):8.2f}  "
              f"最长={max(rl):,}  切换频率={len(rl)/n:7.4%}")
    # 4 个独立分支的"理论错预测率"下界：随机预测器在二值序列上的错率 = min(p,1-p)
    p = ones / n if n else 0
    print(f"  命中位随机猜测错率下界 = min(p,1-p) = {min(p, 1-p):7.2%}")
    # 把 (单独谓词通过, 联合命中) 近似成 baseline 的 4 个分支决策点
    for label, seq in (("① 时间戳", ts_ok), ("② 延迟", lat_ok), ("③ flags", fl_ok)):
        pp = sum(seq) / n
        print(f"  baseline 分支 {label}: 通过率 {pp:7.2%}  "
              f"→ 单分支随机猜测错率下界 {min(pp, 1-pp):7.2%}")
    return hits


if __name__ == "__main__":
    files = sys.argv[1:] or [
        "data/n1m-r50.bin", "data/n2m-b90.bin", "data/n1m-r100.bin",
        "data/n1m-r0.bin", "data/n100000-r50.bin",
    ]
    for f in files:
        p = ROOT / f
        if p.exists():
            analyse(f, p)
        else:
            print(f"(跳过不存在的 {f})")
