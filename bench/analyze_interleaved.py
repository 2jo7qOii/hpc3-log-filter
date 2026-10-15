#!/usr/bin/env python3
"""对 results/interleaved-raw.txt（逐样本交替 A/B）做配对统计分析。

为什么需要配对：原始 A/B 是"先跑完全部 A 再跑完全部 B"，机器的热状态/降频/
容器争用会系统性地偏向其中一边。逐样本交替后，A、B 各自经历相同的热轨迹，
可以用"同一轮的 A/B 配对"来估计加速比，并用配对符号检验给出稳健性判断。
"""
import pathlib, re, statistics as st, random, math, os

ROOT = pathlib.Path(__file__).resolve().parent.parent
import sys
_dir = ROOT / os.environ.get("ANALYSIS_DIR", "results")
_cands = [pathlib.Path(p) for p in sys.argv[1:]] or sorted(
    list(_dir.glob("interleaved-*.txt")) + list(_dir.glob("interleaved-raw.txt")))
TXT = "\n".join(p.read_text() for p in _cands if p.exists())
if not TXT:
    raise SystemExit("找不到交替测量原始文件（先运行 bench/interleaved.sh 或 bench/perf.sh）")


def parse(text):
    """切分成若干实验块：返回 [(name, [(A样本),(B样本),...])]"""
    exps = []
    for chunk in re.split(r"\n(?=### 逐样本交替)", text):
        if not chunk.strip():
            continue
        m = re.search(r"input=(\S+)", chunk)
        name = m.group(1) if m else "?"
        pairs = []
        for line in chunk.splitlines():
            ma = re.search(r"A=\[([^\]]*)\]", line)
            mb = re.search(r"B=\[([^\]]*)\]", line)
            if ma and mb:
                a = [float(x) for x in ma.group(1).split()]
                b = [float(x) for x in mb.group(1).split()]
                if a and b:
                    pairs.append((a, b))
        if pairs:
            exps.append((name, pairs))
    return exps


def sign_test(diffs):
    """双尾二项符号检验：H0 = A 与 B 的耗时无系统差异（每对 50/50）。
    注意：需要对"独立"的配对使用。同轮内的 6 个样本共享热状态，并不独立，
    因此这里同时报告"逐轮配对"（14/8 对，独立性更好）的结果。"""
    n = len([d for d in diffs if d != 0])
    k = len([d for d in diffs if d > 0])          # A 慢于 B 的样本数
    if n == 0:
        return 1.0, 0, 0
    p = 2 * sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n
    return min(1.0, p), k, n


def boot_ci(vals, iters=20000, seed=11):
    rng = random.Random(seed)
    ms = []
    for _ in range(iters):
        ms.append(st.median(rng.choice(vals) for _ in vals))
    ms.sort()
    return ms[int(.025 * iters)], ms[int(.975 * iters)]


for name, pairs in parse(TXT):
    A = [x for a, _ in pairs for x in a]
    B = [x for _, b in pairs for x in b]
    per_round = [st.median(a) / st.median(b) for a, b in pairs]
    diffs = [x - y for a, b in pairs for x, y in zip(a, b)]
    # 同轮配对的 A-B（同热状态）
    print(f"\n{'='*74}\n{name}\n{'='*74}")
    print(f"  样本数 A={len(A)} B={len(B)}  轮数={len(pairs)}")
    print(f"  A: min={min(A):8.3f}  p25={sorted(A)[len(A)//4]:8.3f}  中位={st.median(A):8.3f}  "
          f"均值={st.mean(A):8.3f}  max={max(A):8.3f}")
    print(f"  B: min={min(B):8.3f}  p25={sorted(B)[len(B)//4]:8.3f}  中位={st.median(B):8.3f}  "
          f"均值={st.mean(B):8.3f}  max={max(B):8.3f}")
    lo, hi = boot_ci(A)
    lo2, hi2 = boot_ci(B)
    print(f"  A 中位数 bootstrap 95%CI = [{lo:.3f}, {hi:.3f}]")
    print(f"  B 中位数 bootstrap 95%CI = [{lo2:.3f}, {hi2:.3f}]")
    print(f"  加速比: 中位数之比={st.median(A)/st.median(B):5.2f}×   "
          f"最小值之比={min(A)/min(B):5.2f}×   均值之比={st.mean(A)/st.mean(B):5.2f}×")
    print(f"  逐轮(6 样本中位数)之比: 中位={st.median(per_round):5.2f}×  "
          f"最小={min(per_round):5.2f}×  最大={max(per_round):5.2f}×")
    p, k, n = sign_test(diffs)
    print(f"  配对符号检验(逐样本, 偏乐观): {n} 对中 A 慢的有 {k} 对 ({k/n:.1%})，双尾 p={p:.2e}")
    rp = [1 if st.median(a) > st.median(b) else 0 for a, b in pairs]
    rk = sum(rp)
    rn = len(rp)
    pr = 2 * sum(math.comb(rn, i) for i in range(rk, rn + 1)) / 2 ** rn
    print(f"  配对符号检验(逐轮中位数, 更保守): {rn} 轮中 A 慢的有 {rk} 轮，"
          f"双尾 p={min(1.0, pr):.2e}  → {'显著(p<0.01)' if min(1.0, pr) < 0.01 else '不显著'}")
    sp = [a/b for a, b in zip(A, B)]
    print(f"  逐样本(A/B)比值: 中位={st.median(sp):5.2f}×  "
          f"95%CI=[{sorted(sp)[int(.025*len(sp))]:.2f}, {sorted(sp)[int(.975*len(sp))]:.2f}]"
          f"  （含缓存/调度噪声，故下界偏保守）")
