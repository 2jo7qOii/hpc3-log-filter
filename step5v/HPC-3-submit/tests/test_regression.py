#!/usr/bin/env python3
"""第三关自建回归测试（补充公开测试未覆盖的方向）。

用法: python3 tests/test_regression.py <可执行文件路径>

覆盖点（公开测试的盲区）：
  1. 块边界规模：块大小为 4096，专门测 4095 / 4096 / 4097 / 8192 条；
  2. 不同实现与线程数下输出必须逐字节相同（稳定性的并发不变性）；
  3. 同一输入重复运行结果必须完全一致（确定性）；
  4. 极端字段值：全 0、全 UINT32_MAX、UINT64_MAX 时间戳；
  5. 大样本与参考实现（Python 独立实现）逐条比对，含顺序与全部字段；
  6. 命中率 0% 与 100% 两端：输出条数必须精确为 0 与 N。
"""
import pathlib
import random
import struct
import subprocess
import sys
import tempfile
import unittest

EXE = str(pathlib.Path(sys.argv.pop(1)).resolve()) if len(sys.argv) > 1 else ''
HEADER = struct.Struct('<8sIIQ')
RECORD = struct.Struct('<QIIII')


def encode(rows):
    return HEADER.pack(b'NCULOG01', 1, 24, len(rows)) + b''.join(RECORD.pack(*r) for r in rows)


def decode(data):
    magic, version, width, count = HEADER.unpack_from(data)
    assert (magic, version, width) == (b'NCULOG01', 1, 24), '魔数/版本/宽度不符'
    assert len(data) == 24 + count * 24, '文件长度不符'
    return [RECORD.unpack_from(data, 24 + i * 24) for i in range(count)]


def reference(rows, query):
    """Python 独立实现：稳定筛选（保序、全字段、不去重）。"""
    begin, end, latency, flags = query
    return [r for r in rows if begin <= r[0] < end and r[2] >= latency and (r[4] & flags) == flags]


class Regression(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hpc3-reg-')
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.seq = 0

    def run_case(self, rows, query=(1000, 2000, 100, 3), extra=(), expect_ok=True):
        """跑一次程序，返回 (退出码, 输出字节, stdout)。"""
        self.seq += 1
        src = self.root / f'in{self.seq}.bin'
        dst = self.root / f'out{self.seq}.bin'
        src.write_bytes(encode(rows))
        args = [EXE, '--input', str(src), '--output', str(dst), '--repeats', '2',
                '--begin', str(query[0]), '--end', str(query[1]),
                '--min-latency', str(query[2]), '--flags', str(query[3]), *extra]
        r = subprocess.run(args, capture_output=True, text=True, timeout=120)
        if expect_ok:
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(r.stdout.count('check=PASS'), 2, '核心循环内置校验未全部通过')
            return decode(dst.read_bytes()), r.stdout
        return None, r.stdout

    # ---- 1. 块边界：块大小为 4096，测边界上下各一条 ----
    def test_block_boundaries(self):
        for n in (4095, 4096, 4097, 8192, 8193):
            with self.subTest(n=n):
                rng = random.Random(n)
                rows = [(rng.randrange(900, 2100), i, rng.randrange(80, 130),
                         rng.getrandbits(32), rng.randrange(16)) for i in range(n)]
                got, _ = self.run_case(rows)
                self.assertEqual(got, reference(rows, (1000, 2000, 100, 3)))

    # ---- 2. 不同实现 / 线程数：输出必须逐字节相同 ----
    def test_impl_and_threads_agree(self):
        rng = random.Random(31337)
        rows = [(rng.randrange(900, 2100), i, rng.randrange(80, 130),
                 rng.getrandbits(32), rng.randrange(16)) for i in range(120000)]
        outs = {}
        for tag, extra in (('single', ()),
                           ('twopass1', ('--impl', 'twopass', '--threads', '1')),
                           ('twopass2', ('--impl', 'twopass', '--threads', '2')),
                           ('twopass4', ('--impl', 'twopass', '--threads', '4'))):
            got, _ = self.run_case(rows, extra=extra)
            outs[tag] = got
        base = reference(rows, (1000, 2000, 100, 3))
        for tag, got in outs.items():
            self.assertEqual(got, base, f'{tag} 与参考实现不一致')
        self.assertEqual(len({tuple(o) for o in outs.values()}), 1, '不同实现/线程数结果不一致')

    # ---- 3. 确定性：同输入重复运行结果一致 ----
    def test_deterministic(self):
        rng = random.Random(5)
        rows = [(rng.randrange(900, 2100), i, rng.randrange(80, 130),
                 rng.getrandbits(32), rng.randrange(16)) for i in range(50000)]
        a, _ = self.run_case(rows)
        b, _ = self.run_case(rows)
        self.assertEqual(a, b)

    # ---- 4. 极端字段值 ----
    def test_extreme_fields(self):
        M64, M32 = 2**64 - 1, 2**32 - 1
        rows = [(0, 0, 0, 0, 0),
                (M64, M32, M32, M32, M32),
                (1000, 1, 100, 1, 3),
                (1999, 2, 100, 2, 3),
                (2000, 3, 100, 3, 3),          # 右端开区间：必须排除
                (999, 4, 100, 4, 3),           # 左端闭区间：必须排除
                (1500, 5, 99, 5, 3),           # 延迟不足
                (1500, 6, 100, 6, 1),          # flags 位不全
                (1500, 7, 100, 7, M32)]        # flags 全 1：满足
        for q in [(1000, 2000, 100, 3), (0, M64, 0, 0), (1000, 1000, 0, 0),
                  (M64, M64, M32, M32), (0, 1, 0, M32)]:
            with self.subTest(query=q):
                got, _ = self.run_case(rows, q)
                self.assertEqual(got, reference(rows, q))

    # ---- 5. 大样本差分（含顺序与全部字段）----
    def test_large_differential(self):
        for seed in range(4):
            with self.subTest(seed=seed):
                rng = random.Random(seed)
                n = 30000 + seed * 7777
                rows = [(rng.randrange(0, 3000), i, rng.randrange(0, 1200),
                         rng.getrandbits(32), rng.randrange(32)) for i in range(n)]
                for q in [(1000, 2000, 100, 3), (0, 3000, 0, 0), (1500, 1501, 500, 1)]:
                    got, _ = self.run_case(rows, q)
                    self.assertEqual(got, reference(rows, q), f'seed={seed} q={q}')

    # ---- 6. 命中率 0% / 100% 两端必须精确 ----
    def test_hit_rate_extremes(self):
        dst0 = self.root / 'r0.bin'
        dst100 = self.root / 'r100.bin'
        for rate, dst in ((0, dst0), (100, dst100)):
            if dst.exists():
                dst.unlink()
            subprocess.run([EXE, '--count', '10001', '--hit-percent', str(rate),
                            '--pattern', 'random', '--seed', '17', '--repeats', '1',
                            '--output', str(dst)], capture_output=True, timeout=120, check=True)
            rows = decode(dst.read_bytes())
            self.assertEqual(len(rows), 10001 * rate // 100, f'hit={rate}% 输出条数不对')

    # ---- 7. 参数边界 ----
    def test_argument_edges(self):
        for args in (('--impl', 'bogus'), ('--threads', '0'), ('--threads', '99999')):
            with self.subTest(args=args):
                _, _ = self.run_case([(1500, 1, 100, 1, 3)], extra=args, expect_ok=False)
                r = subprocess.run([EXE, '--count', '10', '--repeats', '1', *args],
                                   capture_output=True, text=True, timeout=60)
                self.assertEqual(r.returncode, 2, f'{args} 应当被拒绝')


if __name__ == '__main__':
    if not EXE:
        raise SystemExit('用法: python3 tests/test_regression.py <可执行文件路径>')
    unittest.main(verbosity=2)
