#!/usr/bin/env python3
"""参数化差分验证：多种命中率/分布/查询下，与 baseline 输出逐字节比对。
用法: python3 bench/diff_check.py --exe ./bench/optimized --base ./bench/baseline --tmp /tmp/dc"""
import argparse, hashlib, pathlib, random, shutil, struct, subprocess, sys

HEADER = struct.Struct('<8sIIQ'); RECORD = struct.Struct('<QIIII')
def encode(rows): return HEADER.pack(b'NCULOG01',1,24,len(rows)) + b''.join(RECORD.pack(*r) for r in rows)

ap = argparse.ArgumentParser()
ap.add_argument('--exe', required=True); ap.add_argument('--base', required=True)
ap.add_argument('--tmp', default='/tmp/diff_check')
a = ap.parse_args()
tmp = pathlib.Path(a.tmp); shutil.rmtree(tmp, ignore_errors=True); tmp.mkdir(parents=True)
exe = str(pathlib.Path(a.exe).resolve()); base = str(pathlib.Path(a.base).resolve())

def run(binary, src, dst, *extra):
    if dst.exists(): dst.unlink()
    r = subprocess.run([binary,'--input',str(src),'--output',str(dst),'--repeats','1',*extra],
                       capture_output=True, text=True, timeout=300)
    if r.returncode != 0: raise SystemExit(f'{binary} 失败: {r.stdout}{r.stderr}')
    return dst.read_bytes()

cases = []
# 1) 各种命中率 × 分布（用程序自带生成器导出固定输入，两种实现各跑一遍对比）
for pattern in ['random','blocks']:
    for rate in [0,1,10,50,90,99,100]:
        cases.append(('gen', dict(count=20000, hit=rate, pattern=pattern)))
# 2) 随机小规模 + 随机查询
rng = random.Random(7)
for seed in range(6):
    n = rng.choice([0,1,2,4095,4096,4097,10000])
    rows = [(rng.randrange(0,3000), i, rng.randrange(0,1200), rng.getrandbits(32), rng.randrange(32))
            for i in range(n)]
    cases.append(('rows', rows, (rng.randrange(0,2500), None, rng.randrange(0,1200), rng.choice([0,1,3,7,15]))))

fails = 0
for i, case in enumerate(cases, 1):
    if case[0] == 'gen':
        p = case[1]; src = tmp/f'g{i}.bin'
        if src.exists(): src.unlink()
        r = subprocess.run([exe,'--count',str(p['count']),'--hit-percent',str(p['hit']),
                            '--pattern',p['pattern'],'--seed','2026','--export-input',str(src),
                            '--repeats','1','--output',str(tmp/f'g{i}.out')],
                           capture_output=True, text=True, timeout=300)
        if r.returncode != 0: raise SystemExit(f'导出输入失败: {r.stdout}{r.stderr}')
        query = ()
    else:
        rows, q = case[1], case[2]
        src = tmp/f'r{i}.bin'; src.write_bytes(encode(rows))
        end = q[1] if q[1] is not None else q[0] + rng.randrange(1, 2000)
        query = ('--begin',str(q[0]),'--end',str(end),'--min-latency',str(q[2]),'--flags',str(q[3]))
    for impl in [[], ['--impl','twopass'], ['--impl','twopass','--threads','2']]:
        ob = run(base, src, tmp/f'{i}-base.out', *query)
        oo = run(exe,  src, tmp/f'{i}-opt.out',  *query, *impl)
        if ob != oo:
            fails += 1
            print(f'❌ 不一致 case={i} impl={impl} {"gen "+str(case[1]) if case[0]=="gen" else "rows"}')
        else:
            print(f'✅ case={i:2d} {"gen hit=%-3d %-6s"%(case[1]["hit"],case[1]["pattern"]) if case[0]=="gen" else "rows n=%-6d"%len(case[1])} impl={"single" if not impl else " ".join(impl[1:])}')
print(f'\n总计 {len(cases)*3} 次比对，失败 {fails} 次')
sys.exit(1 if fails else 0)
