#!/usr/bin/env python3
"""根据 results/ 下的原始样本生成 SVG 图表（不依赖任何第三方库）。

用法: python3 bench/make_charts.py
产出: results/chart-scale.svg      规模扫描：耗时与加速比
      results/chart-hitrate.svg    命中率扫描：耗时与加速比
数据全部来自 results/*.txt 的原始样本，脚本内嵌数值以保证可复现。
"""
import pathlib

OUT = pathlib.Path(__file__).resolve().parent.parent / 'results'
OUT.mkdir(exist_ok=True)

# ---------------------------------------------------------------- 数据
# 以下数值全部取自 results/scale-sweep.txt 与 results/ab-*.txt 的原始样本，
# 每点 = 同一会话内 A/B 交替重复、每组 5 次采样中的最小值。
#
# 规模扫描（命中率 50%、random 分布）：(记录数, baseline 最好 ms, optimized 最好 ms)
SCALE = [
    (100_000,    0.75,  0.30),
    (250_000,    1.83,  0.88),
    (500_000,    3.75,  1.75),
    (1_000_000,  7.85,  3.79),
    (2_000_000, 16.80,  7.45),
    (10_000_000, 95.23, 51.75),
]
# 命中率扫描（1M、random）：(标签, baseline 最好 ms, optimized 最好 ms)
HIT = [
    ('0%',   10.48, 5.10),
    ('50%',  7.85,  3.79),   # 与规模扫描的 1M 点同源
    ('90%-blocks', 13.20, 12.95),
    ('100%', 6.23,  6.87),
]

W, H = 760, 420
PAD_L, PAD_R, PAD_T, PAD_B = 78, 78, 46, 58


def esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def chart(path, title, xs, xlabels, series, ylab, y2lab, note):
    """series: [(名称, 颜色, [值...]), ...]；前两条画左轴，第三条画右轴（加速比）。"""
    n = len(xs)
    x0, x1 = 0, n - 1
    ymax1 = max(max(v for _, _, vals in series[:2] for v in vals) * 1.15, 1e-9)
    ymax2 = max(series[2][2]) * 1.35 if len(series) > 2 else 1.0

    def px(i):
        return PAD_L + (W - PAD_L - PAD_R) * (i - x0) / max(x1 - x0, 1)

    def py(v):
        return H - PAD_B - (H - PAD_T - PAD_B) * v / ymax1

    def py2(v):
        return H - PAD_B - (H - PAD_T - PAD_B) * v / ymax2

    g = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
         f'viewBox="0 0 {W} {H}" font-family="DejaVu Sans, Arial, sans-serif">',
         f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
         f'<text x="{W//2}" y="26" text-anchor="middle" font-size="17" font-weight="bold">{esc(title)}</text>']

    # 网格与左轴刻度
    for k in range(6):
        v = ymax1 * k / 5
        y = py(v)
        g.append(f'<line x1="{PAD_L}" y1="{y:.1f}" x2="{W-PAD_R}" y2="{y:.1f}" stroke="#e6e6e6"/>')
        g.append(f'<text x="{PAD_L-8}" y="{y+4:.1f}" text-anchor="end" font-size="11" fill="#555">{v:.0f}</text>')
    # 右轴刻度
    if len(series) > 2:
        for k in range(6):
            v = ymax2 * k / 5
            y = py2(v)
            g.append(f'<text x="{W-PAD_R+8}" y="{y+4:.1f}" font-size="11" fill="#c1440e">{v:.1f}</text>')

    g.append(f'<text x="20" y="{PAD_T-16}" font-size="12" fill="#333">{esc(ylab)}</text>')
    if len(series) > 2:
        g.append(f'<text x="{W-20}" y="{PAD_T-16}" text-anchor="end" font-size="12" fill="#c1440e">{esc(y2lab)}</text>')
    g.append(f'<line x1="{PAD_L}" y1="{H-PAD_B}" x2="{W-PAD_R}" y2="{H-PAD_B}" stroke="#999"/>')

    for i, lab in enumerate(xlabels):
        g.append(f'<text x="{px(i):.1f}" y="{H-PAD_B+18}" text-anchor="middle" font-size="11" fill="#555">{esc(lab)}</text>')

    for name, color, vals in series:
        f = py if name != series[2][0] else py2
        pts = ' '.join(f'{px(i):.1f},{f(v):.1f}' for i, v in enumerate(vals))
        dash = ' stroke-dasharray="6 3"' if name == series[2][0] else ''
        g.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2.4"{dash}/>')
        for i, v in enumerate(vals):
            g.append(f'<circle cx="{px(i):.1f}" cy="{f(v):.1f}" r="3.6" fill="{color}"/>')
            if name == series[2][0]:
                dy = -9 if v >= 1.6 else 15      # 加速比接近 1 时标在下方，避免与折线重叠
                g.append(f'<text x="{px(i):.1f}" y="{f(v)+dy:.1f}" text-anchor="middle" '
                         f'font-size="10" fill="{color}">{v:.2f}x</text>')

    # 图例
    lx = PAD_L + 6
    for name, color, _ in series:
        g.append(f'<line x1="{lx}" y1="{PAD_T-24}" x2="{lx+22}" y2="{PAD_T-24}" stroke="{color}" stroke-width="2.6"/>')
        g.append(f'<text x="{lx+28}" y="{PAD_T-20}" font-size="11.5" fill="#333">{esc(name)}</text>')
        lx += 34 + 8 * len(name) + 16
    g.append(f'<text x="{W//2}" y="{H-14}" text-anchor="middle" font-size="11" fill="#666">{esc(note)}</text>')
    g.append('</svg>')
    path.write_text('\n'.join(g), encoding='utf-8')
    print(f'已生成 {path}')


scale_labels = [f'{n//1000}k' if n < 1_000_000 else f'{n//1_000_000}M' for n, _, _ in SCALE]
chart(OUT / 'chart-scale.svg',
      '规模扫描：核心筛选耗时与加速比（命中率 50%、random 分布）',
      [n for n, _, _ in SCALE], scale_labels,
      [('baseline（原始）', '#4a6fa5', [b for _, b, _ in SCALE]),
       ('optimized（本实现）', '#2e8b57', [o for _, _, o in SCALE]),
       ('加速比', '#c1440e', [b / o for _, b, o in SCALE])],
      '耗时 (ms，越低越好)', '加速比 (x)',
      '每点 = 同一会话内 A/B 交替重复、5 次采样中的最小值。原始样本见 results/scale-sweep.txt')

hit_labels = [h for h, _, _ in HIT]
chart(OUT / 'chart-hitrate.svg',
      '命中率扫描：核心筛选耗时与加速比（100 万条、random 分布）',
      list(range(len(HIT))), hit_labels,
      [('baseline（原始）', '#4a6fa5', [b for _, b, _ in HIT]),
       ('optimized（本实现）', '#2e8b57', [o for _, _, o in HIT]),
       ('加速比', '#c1440e', [b / o for _, b, o in HIT])],
      '耗时 (ms，越低越好)', '加速比 (x)',
      '50% 与 90% 为不同数据集（90% 兼为 blocks 分布）；0%/100% 为精确边界。原始样本见 results/ab-*.txt')
