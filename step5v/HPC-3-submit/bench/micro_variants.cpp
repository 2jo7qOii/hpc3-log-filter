// ============================================================================
//  micro_variants.cpp —— 独立复现实验：把"单遍无分支"优化拆成可单独开关的步骤
//
//  目的：验证 REPORT.md 的因果解释（阈值局部化 / 无分支搬运各贡献多少），
//        而不是只看 baseline 与最终实现的整体差。
//
//  与被测评程序的区别（刻意为之）：
//    * filter 函数放在另一个翻译单元（micro_core.cpp），避免编译器跨过程内联后
//      把被测循环优化掉；
//    * 同一进程内按"轮次 × 变体"交替执行，所有变体共享同一份输入、同一时段；
//    * 每轮开始前把输入缓冲刷出缓存，保证测的是真实内存访问。
//
//  编译：g++ -O2 -std=c++17 -pthread -mclflushopt bench/micro_variants.cpp bench/micro_core.cpp -I src -o bench/micro_variants
// ============================================================================
#include "support.hpp"

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <immintrin.h>
#include <iomanip>
#include <iostream>
#include <string>
#include <vector>

std::size_t v_baseline(const Record*, std::size_t, Record*, const Query&);
std::size_t v_local_thresholds(const Record*, std::size_t, Record*, const Query&);
std::size_t v_shortcircuit(const Record*, std::size_t, Record*, const Query&);
std::size_t v_branchless_cmov(const Record*, std::size_t, Record*, const Query&);
std::size_t v_branchless_guarded(const Record*, std::size_t, Record*, const Query&);

struct Variant { const char* name; std::size_t (*fn)(const Record*, std::size_t, Record*, const Query&); };

static void flush_cache(Record* p, std::size_t n) {
    char* base = reinterpret_cast<char*>(p);
    const std::size_t bytes = n * sizeof(Record);
    for (std::size_t off = 0; off < bytes; off += 64) _mm_clflushopt(base + off);
    _mm_sfence();
}

int main(int argc, char** argv) {
    const std::string path = (argc > 1) ? argv[1] : "data/n1m-r50.bin";
    const unsigned rounds = (argc > 2) ? static_cast<unsigned>(std::stoul(argv[2])) : 12;
    const Query q;

    std::cout << "\n########## " << path << " ##########\n"
              << "### 微基准变体对比  input=" << path << " rounds=" << rounds
              << " query=[" << q.begin << "," << q.end << ") lat>=" << q.min_latency_us
              << " flags=" << q.required_flags << "\n";
    auto input = load(path, 100000000ull);
    std::vector<Record> out(input.size());
    const auto expected = reference_filter(input, q);
    std::cout << "### count=" << input.size() << " expected_hits=" << expected.size() << "\n";

    const Variant variants[] = {
        {"1_baseline_4cmp",        v_baseline},
        {"2_baseline_localthr",    v_local_thresholds},
        {"3_shortcircuit_mask",    v_shortcircuit},
        {"4_branchless_cmov",      v_branchless_cmov},
        {"5_branchless_guarded",   v_branchless_guarded},
    };
    const unsigned NV = sizeof(variants) / sizeof(variants[0]);

    // 正确性检查（每个变体都必须给出完全相同的输出，含顺序与全部字段）
    for (unsigned v = 0; v < NV; ++v) {
        std::fill(out.begin(), out.end(), Record{});
        const std::size_t n = variants[v].fn(input.data(), input.size(), out.data(), q);
        bool ok = (n == expected.size());
        for (std::size_t i = 0; ok && i < n; ++i) ok = equal_record(out[i], expected[i]);
        std::cout << "### check " << variants[v].name << " hits=" << n << (ok ? "  PASS" : "  FAIL") << "\n";
    }

    // 计时：轮次为外层、变体为内层 —— 同轮内共享热状态，轮次间相互独立
    std::vector<std::vector<double>> times(NV);
    for (unsigned r = 0; r < rounds; ++r) {
        for (unsigned v = 0; v < NV; ++v) {
            flush_cache(input.data(), input.size());
            const auto t0 = std::chrono::steady_clock::now();
            const std::size_t n = variants[v].fn(input.data(), input.size(), out.data(), q);
            const double ms = std::chrono::duration<double, std::milli>(
                                  std::chrono::steady_clock::now() - t0).count();
            if (n != expected.size()) { std::cerr << "count mismatch\n"; return 2; }
            times[v].push_back(ms);
        }
    }

    std::cout << std::fixed << std::setprecision(3);
    std::cout << "\n变体                         min      median   (ms)   全部样本\n";
    for (unsigned v = 0; v < NV; ++v) {
        auto t = times[v];
        std::sort(t.begin(), t.end());
        std::cout << std::left << std::setw(24) << variants[v].name << std::right
                  << std::setw(9) << t.front() << std::setw(12) << t[t.size() / 2] << "   ";
        for (double x : times[v]) std::cout << x << ' ';
        std::cout << '\n';
    }
    return 0;
}
