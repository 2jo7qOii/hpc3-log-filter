#!/usr/bin/env python3
"""从原始样本直接重画图表（对应"第四轮：规模扫描 + 图表"）。

与 bench/make_charts.py 的区别（这也是它存在的理由）：
  make_charts.py        数值**内嵌**在脚本里 —— 保证图表与报告逐字节一致，
                        但换了机器/重跑了 perf.sh 之后，图表不会跟着变。
  charts_from_data.py   数值**现读** results/ 或 results/ab-live/ 的原始样本 ——
                        因此"重跑 → 重新出图"是闭环的。两者互为交叉校验：
                        如果两者画出的数字不一致，说明有人手改过内嵌数值。

用法:
  python3 bench/charts_from_data.py                     # 读 results/
  ANALYSIS_DIR=results/ab-live python3 bench/charts_from_data.py

输入（缺失的自动跳过，不报错）:
  <dir>/scale-sweep.txt        规模扫描（A/B 交替，每轮 5 次）
  <dir>/ab-2m-b90.txt          命中率 90%（blocks 分布）
  <dir>/ab-1m-r50.txt          命中率 50%
  <dir>/ab-1m-r0.txt           命中率 0%（v4 起缺失 → 该点画不出来，脚本会提示）
  <dir>/ab-1m-r100.txt         命中率 100%（同上）
产出:
  <dir>/chart-scale-data.svg / chart-hitrate-data.svg
  （文件名带 -data，刻意不覆盖交付用的 chart-*.svg）
"""
import os
import pathlib
import re
import statistics as st

RES = pathlib.Path(__file__).resolve().parent.parent / os.environ.get("ANALYSIS_DIR", "results")
ROUND_RE = re.compile(r"round=(\d+)\s+impl=([AB])\s+best=([\d.]+)\s+median=([\d.]+)\s+samples=\[\s*(.*?)\]")
NUM_RE = re.compile(r"[\d.]+")


def parse_ab(path):
    """-> {轮号: {'A': [...], 'B': [...]}}；数值取自 samples=[...] 原始样本。"""
    out = {}
    if not path.exists():
        return out
    for line in path.read_text(errors="replace").splitlines():
        m = ROUND_RE.search(line)
        if m:
            out.setdefault(int(m.group(1)), {})[m.group(2)] = \
                [float(x) for x in NUM_RE.findall(m.group(5))]
    return out


def best_of(data, tag):
    """跨轮最小值（与报告口径一致）。"""
    vals = [min(data[r][tag]) for r in sorted(data) if tag in data[r] and data[r][tag]]
    return min(vals) if vals else None


def parse_scale_sweep(path):
    """-> [(数据集名, 记录数, baseline 最好, optimized 最好)]"""
    if not path.exists():
        return []
    txt = path.read_text(errors="replace")
    parts = re.split(r"=====\s+(\S+)\s+\((\d+) 字节\)\s+=====", txt)
    rows = []
    for i in range(1, len(parts), 3):
        name, size, body = parts[i], int(parts[i + 1]), parts[i + 2]
        tmp = path.parent / f".tmp-{name}"
        tmp.write_text(body)
        data = parse_ab(tmp)
        tmp.unlink()
        a, b = best_of(data, "A"), best_of(data, "B")
        if a and b:
            # 记录数从数据集名里取（n100000-r50 → 100000；n10m-r50 → 10000000）
            m = re.match(r"n(\d+)([mM]?)-", name)
            n = int(m.group(1)) * (1_000_000 if m.group(2) else 1) if m else size // 24
            rows.append((name, n, a, b))
    rows.sort(key=lambda r: r[1])
    return rows


# ---------------------------------------------------------------- 画图（纯 SVG，无第三方库）
W, H = 760, 420
PAD_L, PAD_R, PAD_T, PAD_B = 78, 78, 46, 58


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def chart(path, title, xlabels, series, ylab, y2lab, note):
    n = len(xlabels)
    ymax1 = max(max(v for _, _, vals in series[:2] for v in vals) * 1.15, 1e-9)
    ymax2 = max(series[2][2]) * 1.35
    px = lambda i: PAD_L + (W - PAD_L - PAD_R) * i / max(n - 1, 1)
    py = lambda v: H - PAD_B - (H - PAD_T - PAD_B) * v / ymax1
    py2 = lambda v: H - PAD_B - (H - PAD_T - PAD_B) * v / ymax2

    g = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
         f'font-family="DejaVu Sans, Arial, sans-serif">',
         f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
         f'<text x="{W//2}" y="26" text-anchor="middle" font-size="17" font-weight="bold">{esc(title)}</text>']
    for k in range(6):
        v, y = ymax1 * k / 5, py(ymax1 * k / 5)
        g.append(f'<line x1="{PAD_L}" y1="{y:.1f}" x2="{W-PAD_R}" y2="{y:.1f}" stroke="#e6e6e6"/>')
        g.append(f'<text x="{PAD_L-8}" y="{y+4:.1f}" text-anchor="end" font-size="11" fill="#555">{v:.0f}</text>')
        v2, y2 = ymax2 * k / 5, py2(ymax2 * k / 5)
        g.append(f'<text x="{W-PAD_R+8}" y="{y2+4:.1f}" font-size="11" fill="#c1440e">{v2:.1f}</text>')
    g.append(f'<text x="20" y="{PAD_T-16}" font-size="12" fill="#333">{esc(ylab)}</text>')
    g.append(f'<text x="{W-20}" y="{PAD_T-16}" text-anchor="end" font-size="12" fill="#c1440e">{esc(y2lab)}</text>')
    g.append(f'<line x1="{PAD_L}" y1="{H-PAD_B}" x2="{W-PAD_R}" y2="{H-PAD_B}" stroke="#999"/>')
    for i, lab in enumerate(xlabels):
        g.append(f'<text x="{px(i):.1f}" y="{H-PAD_B+18}" text-anchor="middle" font-size="11" fill="#555">{esc(lab)}</text>')
    for name, color, vals in series:
        f = py2 if name == series[2][0] else py
        pts = " ".join(f"{px(i):.1f},{f(v):.1f}" for i, v in enumerate(vals))
        dash = ' stroke-dasharray="6 3"' if name == series[2][0] else ""
        g.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2.4"{dash}/>')
        for i, v in enumerate(vals):
            g.append(f'<circle cx="{px(i):.1f}" cy="{f(v):.1f}" r="3.6" fill="{color}"/>')
            if name == series[2][0]:
                dy = -9 if v >= 1.6 else 15
                g.append(f'<text x="{px(i):.1f}" y="{f(v)+dy:.1f}" text-anchor="middle" '
                         f'font-size="10" fill="{color}">{v:.2f}x</text>')
    lx = PAD_L + 6
    for name, color, _ in series:
        g.append(f'<line x1="{lx}" y1="{PAD_T-24}" x2="{lx+22}" y2="{PAD_T-24}" stroke="{color}" stroke-width="2.6"/>')
        g.append(f'<text x="{lx+28}" y="{PAD_T-20}" font-size="11.5" fill="#333">{esc(name)}</text>')
        lx += 34 + 8 * len(name) + 16
    g.append(f'<text x="{W//2}" y="{H-14}" text-anchor="middle" font-size="11" fill="#666">{esc(note)}</text>')
    g.append("</svg>")
    path.write_text("\n".join(g), encoding="utf-8")
    print(f"已生成 {path}")


def main():
    print(f"数据目录: {RES}")
    rows = parse_scale_sweep(RES / "scale-sweep.txt")
    if rows:
        labels = [f"{n//1000}k" if n < 1_000_000 else f"{n//1_000_000}M" for _, n, _, _ in rows]
        print("规模扫描（跨轮最小值）:")
        for (nm, n, a, b) in rows:
            print(f"  {nm:<16} baseline={a:8.3f}  optimized={b:8.3f}  加速比={a/b:5.2f}x")
        chart(RES / "chart-scale-data.svg",
              "规模扫描：核心筛选耗时与加速比（命中率 50%、random 分布）",
              labels,
              [("baseline（原始）", "#4a6fa5", [a for _, _, a, _ in rows]),
               ("optimized（本实现）", "#2e8b57", [b for _, _, _, b in rows]),
               ("加速比", "#c1440e", [a / b for _, _, a, b in rows])],
              "耗时 (ms，越低越好)", "加速比 (x)",
              f"每点 = 跨轮最小值；原始样本 {RES.name}/scale-sweep.txt")
    else:
        print(f"!! 未找到 {RES/'scale-sweep.txt'}，跳过规模图")

    # 命中率扫描：读得到哪个点画哪个点
    specs = [("0%", "ab-1m-r0.txt"), ("50%", "ab-1m-r50.txt"),
             ("90%-blocks", "ab-2m-b90.txt"), ("100%", "ab-1m-r100.txt")]
    hit = []
    for label, fname in specs:
        data = parse_ab(RES / fname)
        a, b = best_of(data, "A"), best_of(data, "B")
        if a and b:
            hit.append((label, a, b))
        else:
            print(f"!! 缺少 {fname} → 命中率图中「{label}」这一点无法重画（v4 的 chart-hitrate.svg "
                  f"里该点数值为脚本内嵌，仓库内无对应原始样本）")
    if hit:
        print("命中率扫描（跨轮最小值）:")
        for lab, a, b in hit:
            print(f"  {lab:<12} baseline={a:8.3f}  optimized={b:8.3f}  加速比={a/b:5.2f}x")
        chart(RES / "chart-hitrate-data.svg",
              "命中率扫描：核心筛选耗时与加速比（100 万条、random 分布）",
              [h for h, _, _ in hit],
              [("baseline（原始）", "#4a6fa5", [a for _, a, _ in hit]),
               ("optimized（本实现）", "#2e8b57", [b for _, _, b in hit]),
               ("加速比", "#c1440e", [a / b for _, a, b in hit])],
              "耗时 (ms，越低越好)", "加速比 (x)",
              f"每点 = 跨轮最小值；仅有 {len(hit)}/{len(specs)} 个点存在原始样本")
    else:
        print("!! 没有任何 ab-*.txt 命中率样本，跳过命中率图")


if __name__ == "__main__":
    main()
