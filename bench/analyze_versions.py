#!/usr/bin/env python3
"""对 results/ 下的原始样本做独立的统计分析（不改动任何数据，只读）。

输出：
  * 每个数据集的 A(baseline)/B(optimized) 统计量：min / median / p25 / p75 / max / CV
  * 加速比（按跨轮最小值、按全局最小值、按合并样本中位数）与 bootstrap 95% 置信区间
  * 噪声诊断：批内离散度 vs 批间漂移
"""
import pathlib, re, statistics as st, random, json, os

ROOT = pathlib.Path(__file__).resolve().parent.parent
# 结果目录可用环境变量覆盖：新的复现写入 results/ab-live/，不覆盖已有证据文件
RES = ROOT / os.environ.get("ANALYSIS_DIR", "results")

ROUND_RE = re.compile(
    r"round=(\d+)\s+impl=([AB])\s+best=([\d.]+)\s+median=([\d.]+)\s+samples=\[\s*(.*?)\]")
SAMPLE_RE = re.compile(r"[\d.]+")


def parse_ab(path):
    """返回 {round: {'A': [samples], 'B': [samples]}}, 以及文件头信息"""
    out, rounds = {}, []
    for line in path.read_text().splitlines():
        m = ROUND_RE.search(line)
        if not m:
            continue
        rnd, impl, best, med, s = int(m.group(1)), m.group(2), float(m.group(3)), \
            float(m.group(4)), [float(x) for x in SAMPLE_RE.findall(m.group(5))]
        out.setdefault(rnd, {})[impl] = s
        rounds.append((rnd, impl, best, med, len(s)))
    return out


def q(v, p):
    v = sorted(v)
    if not v:
        return float("nan")
    k = (len(v) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


def describe(v):
    if not v:
        return {}
    m = st.mean(v)
    sd = st.stdev(v) if len(v) > 1 else 0.0
    return dict(n=len(v), min=min(v), p25=q(v, .25), median=st.median(v),
                p75=q(v, .75), max=max(v), mean=m, sd=sd, cv=(sd / m if m else 0.0))


def boot_speedup(a, b, iters=20000, seed=7):
    """按 min 判据的加速比置信区间：分别对两组样本重采样再取 min。"""
    rng = random.Random(seed)
    rs = []
    for _ in range(iters):
        ma = min(rng.choice(a) for _ in a)
        mb = min(rng.choice(b) for _ in b)
        if mb > 0:
            rs.append(ma / mb)
    rs.sort()
    return q(rs, .025), st.median(rs), q(rs, .975)


def report(name, data, note=""):
    A = [x for r in sorted(data) for x in data[r].get("A", [])]
    B = [x for r in sorted(data) if "B" in data[r] for x in data[r]["B"]]
    # 跨轮最小值：每轮 5 次取 min，再跨轮取 min
    bestA = min(min(data[r]["A"]) for r in data if "A" in data[r])
    bestB = min(min(data[r]["B"]) for r in data if "B" in data[r])
    medA = min(st.median(data[r]["A"]) for r in data if "A" in data[r])
    medB = min(st.median(data[r]["B"]) for r in data if "B" in data[r])
    da, db = describe(A), describe(B)
    lo, mid, hi = boot_speedup(A, B) if A and B else (0, 0, 0)
    print(f"\n=== {name} {note} ===")
    print(f"  baseline : {da['n']:>3} 样本  min={da['min']:8.3f}  p25={da['p25']:8.3f}  "
          f"median={da['median']:8.3f}  p75={da['p75']:8.3f}  max={da['max']:9.3f}  CV={da['cv']*100:5.1f}%")
    print(f"  optimized: {db['n']:>3} 样本  min={db['min']:8.3f}  p25={db['p25']:8.3f}  "
          f"median={db['median']:8.3f}  p75={db['p75']:8.3f}  max={db['max']:9.3f}  CV={db['cv']*100:5.1f}%")
    print(f"  加速比: 跨轮最小值 {bestA/bestB:5.2f}× (A={bestA:.3f} B={bestB:.3f}) | "
          f"全局最小值 {da['min']/db['min']:5.2f}× | 合并中位数 {da['median']/db['median']:5.2f}× | "
          f"bootstrap(min 判据) 95%CI [{lo:.2f}, {hi:.2f}] 中位 {mid:.2f}")
    return dict(name=name, A=da, B=db, bestA=bestA, bestB=bestB,
                speed_min_round=bestA / bestB, speed_min_all=da["min"] / db["min"],
                speed_median=da["median"] / db["median"], ci=[lo, hi])


def parse_ab_files(res_dir):
    """自动收集目录下所有 A/B 原始样本文件（scale-sweep 与 ab-*.txt 分开处理）。"""
    found = sorted(p for p in res_dir.glob("ab-*.txt"))
    return found


def parse_scale_sweep():
    txt = (RES / "scale-sweep.txt").read_text()
    blocks = re.split(r"=====\s+(\S+)\s+\((\d+) 字节\)\s+=====", txt)
    res = {}
    for i in range(1, len(blocks), 3):
        name, size, body = blocks[i], int(blocks[i + 1]), blocks[i + 2]
        tmp = RES / f".tmp-{name}"
        tmp.write_text(body)
        res[name] = (parse_ab(tmp), size)
        tmp.unlink()
    return res


def main():
    rows = []
    print("#" * 78)
    print("# 1. 规模扫描（同一会话，A/B 交替，命中率 50% random）")
    print("#" * 78)
    sweep = parse_scale_sweep()
    if not sweep:
        print(f"  （{RES}/scale-sweep.txt 不存在，跳过；先跑 bench/perf.sh 或 bench/run_all.sh）")
    for name, (data, size) in sweep.items():
        rows.append(report(name, data, f"({size/1e6:.1f} MB 输入)"))

    print("\n" + "#" * 78)
    print("# 2. 其余 A/B 实验")
    print("#" * 78)
    ab_files = parse_ab_files(RES)
    if not ab_files:
        print(f"  （{RES} 下没有 ab-*.txt，跳过；用 bench/bench_run.sh 或 bench/perf.sh 生成）")
    for f in ab_files:
        rows.append(report(f.name, parse_ab(f)))

    print("\n" + "#" * 78)
    print("# 3. 汇总表（按跨轮最小值）")
    print("#" * 78)
    print(f"{'数据集':<22}{'baseline':>11}{'optimized':>12}{'加速比':>9}{'CI95%下界':>11}")
    for r in rows:
        print(f"{r['name']:<22}{r['bestA']:>11.3f}{r['bestB']:>12.3f}"
              f"{r['speed_min_round']:>8.2f}×{r['ci'][0]:>10.2f}×")

    print("\n" + "#" * 78)
    print("# 4. 噪声结构与吞吐")
    print("#" * 78)
    for r in rows:
        da, db = r["A"], r["B"]
        print(f"{r['name']:<22} 批内最大/最小(baseline)={da['max']/da['min']:5.2f}×  "
              f"(optimized)={db['max']/db['min']:5.2f}×   "
              f"吞吐 A={1e3/da['min']:6.1f} B={1e3/db['min']:6.1f} Mrec/s")

    print("\n" + "#" * 78)
    print("# 5. 线程扩展性（10M, twopass）")
    print("#" * 78)
    tpath = RES / "exp-threads-10m.txt"
    if not tpath.exists():
        print("  （缺 exp-threads-10m.txt，跳过）")
        json.dump(rows, open(RES / "analysis-versions.json", "w"), ensure_ascii=False, indent=1)
        print(f"\n(表格数据已写入 {RES}/analysis-versions.json)")
        return
    t = tpath.read_text()
    cur = None
    for line in t.splitlines():
        if line.startswith("---"):
            cur = line.strip("- ").strip()
        m = re.search(r"core_ms=([\d.]+)", line)
        if m and cur:
            print(f"  {cur:<12} {float(m.group(1)):9.3f} ms")
        m2 = re.search(r"median_core_ms=([\d.]+)", line)
        if m2:
            print(f"  {cur:<12} 中位数 {float(m2.group(1)):.3f} ms")

    json.dump(rows, open(RES / "analysis-versions.json", "w"),
              ensure_ascii=False, indent=1)
    print(f"\n(表格数据已写入 {RES}/analysis-versions.json)")


if __name__ == "__main__":
    main()
