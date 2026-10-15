// ============================================================================
//  optimized.cpp —— 第三关：日志压缩与稳定筛选优化
//
//  编译：g++ -O2 -std=c++17 -pthread src/optimized.cpp -I src -o bench/optimized
//  运行：./bench/optimized --input data/n1m-r50.bin --output out/result.bin --repeats 5
//
//  设计要点（详见 REPORT.md 第 3、4、5 节）：
//    * 核心接口 filter_records 保持题目规定的签名与语义：稳定、全字段、不去重。
//    * 默认实现 "single"：单遍扫描 + 无分支搬运。实测在本机（2 核）最快。
//    * 备选实现 "twopass"：分块计数 + 前缀和 + 分块写出（可多线程）。
//      该方案是题目分层提示推荐的思路；本实现保留它，并如实报告其在本机的劣势。
//    * 临时内存只有 O(块数) 的前缀和数组（10^7 条数据下约 19 KiB）；单遍方案 O(1)。
// ============================================================================

#include "support.hpp"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstddef>
#include <iomanip>
#include <iostream>
#include <set>
#include <string>
#include <thread>
#include <vector>

// ============================================================================
//  公共部分
// ============================================================================

namespace tune {
// 两遍方案里每块的记录条数：4096 × 24B = 96 KiB。
// 只影响速度，不影响任何结果。
constexpr std::size_t kBlock = 1u << 12;
}

// 判断"这一条记录要不要留下"。
// 四个条件全满足才为 true：时间戳在区间内、延迟达标、flags 含要求的全部位。
inline bool record_matches(const Record& r, const Query& q) noexcept {
    // 时间戳在 [begin, end) 之间（右端是开区间）
    return r.timestamp >= q.begin && r.timestamp < q.end &&
           // 延迟达到下限
           r.latency_us >= q.min_latency_us &&
           // flags 必须包含要求的全部位
           (r.flags & q.required_flags) == q.required_flags;
}

// ============================================================================
//  实现一（默认）：单遍扫描 + 无分支搬运
//
//  与 baseline 的算法相同（只扫一遍输入），区别只在"判断"的写法：
//    baseline：四个 if(...) continue;  —— 四个独立分支，处理器反复猜错路
//    本实现  ：先算出 ok ∈ {0,1}，再无条件下标写、写指针只前进 ok
//              out[m] = r;  m += ok;
//              命中时 m 前进 1（这条记录留在输出里）；
//              未命中时 m 不动，下一次写会覆盖这个位置（等于丢弃）。
//
//  为什么仍然保持稳定顺序：
//    写出位置由 m 单调解出，第 i 条记录一定写在所有更早的命中记录之后，
//    因此输出的先后顺序严格等于输入顺序。
//
//  为什么 output == input（原地压缩）也安全：
//    写指针 m 恒满足 m <= i，永远只覆盖已经读过的位置，不会破坏未读数据。
//    （题目接口约定两者不重叠，这里只是说明额外余量。）
// ============================================================================
static std::size_t filter_single_pass(const Record* input, std::size_t count,
                                      Record* output, const Query& query) {
    // 把查询条件取到局部变量：循环里就不必每轮再从内存读 Query 的四个字段。
    // 实测这一项就能带来约 26% 的提升（中位数 19.1ms -> 15.1ms，10^6 条）。
    const std::uint64_t q_begin = query.begin;
    const std::uint64_t q_end   = query.end;
    const std::uint32_t q_lat   = query.min_latency_us;
    const std::uint32_t q_flags = query.required_flags;

    std::size_t m = 0;                       // 已写出的条数 = 下一个写出位置
    for (std::size_t i = 0; i < count; ++i) {
        const Record& r = input[i];
        // 一次算出 0/1，而不是让处理器去猜分支
        const unsigned ok = (unsigned)(r.timestamp >= q_begin) & (unsigned)(r.timestamp < q_end)
                          & (unsigned)(r.latency_us >= q_lat)
                          & (unsigned)((r.flags & q_flags) == q_flags);
        output[m] = r;                       // 无条件写：未命中时写的是即将被覆盖的位置
        m += ok;                             // 命中才把写指针往前推
    }
    return m;
}

// ============================================================================
//  实现二（备选，用于对比）：分块计数 + 排他前缀和 + 分块写出
//
//  第一遍：按块统计每块命中数（只读不写）
//  前缀和：把"每块命中数"就地改写成"每块的输出起始位置"
//  第二遍：按块序写出，块内保持输入顺序
//
//  稳定性的依据：各块输出区间由前缀和精确划分、互不重叠，且块序、块内次序
//  都与输入顺序一致。
//
//  该实现存在的意义：
//    1) 它是题目分层提示推荐的方案，实现并实测后放入报告对比；
//    2) 前缀和使各块可以并行且无写冲突（见下面的线程版本）；
//    3) 实测在本机（2 核）反而慢于单遍方案，原因见 REPORT.md 第 5 节。
// ============================================================================

// 第一遍：统计 [lo, hi) 区间内的命中数（只读，无分支累加）
static std::size_t count_hits(const Record* in, std::size_t lo, std::size_t hi, const Query& q) {
    std::size_t hits = 0;
    for (std::size_t i = lo; i < hi; ++i)
        hits += record_matches(in[i], q) ? 1u : 0u;
    return hits;
}

// 第二遍：把 [lo, hi) 这些块按各自的起始位置写出
static void write_blocks(const Record* in, std::size_t lo, std::size_t hi, std::size_t count,
                         Record* out, const std::size_t* starts, const Query& q) {
    for (std::size_t b = lo; b < hi; ++b) {
        const std::size_t from = b * tune::kBlock;
        const std::size_t to   = std::min(from + tune::kBlock, count);
        Record* w = out + starts[b];                 // 本块的输出起点（由前缀和给定）
        for (std::size_t i = from; i < to; ++i) {
            const Record& r = in[i];
            if (record_matches(r, q)) *w++ = r;      // 块内顺序写出
        }
    }
}

static std::size_t filter_two_pass(const Record* input, std::size_t count,
                                   Record* output, const Query& query, unsigned threads) {
    if (count == 0) return 0;

    const std::size_t nblocks = (count + tune::kBlock - 1) / tune::kBlock;
    std::vector<std::size_t> starts(nblocks + 1, 0);   // 前 nblocks 个存起始位置，末位存总数

    // 线程任务划分：每线程负责一段连续的块
    const std::size_t nt = (threads == 0) ? 1 : std::min<std::size_t>(threads, nblocks);
    const std::size_t base = nblocks / nt, extra = nblocks % nt;
    const auto bound = [base, extra](std::size_t t) { return base * t + std::min(t, extra); };

    // ---- 第一遍：计数 ----
    if (nt <= 1) {
        for (std::size_t b = 0; b < nblocks; ++b)
            starts[b] = count_hits(input, b * tune::kBlock,
                                   std::min((b + 1) * tune::kBlock, count), query);
    } else {
        std::vector<std::thread> pool;
        pool.reserve(nt - 1);
        for (std::size_t t = 1; t < nt; ++t)
            pool.emplace_back([&, t] {
                for (std::size_t b = bound(t); b < bound(t + 1); ++b)
                    starts[b] = count_hits(input, b * tune::kBlock,
                                           std::min((b + 1) * tune::kBlock, count), query);
            });
        for (std::size_t b = bound(0); b < bound(1); ++b)     // 主线程承担第一份
            starts[b] = count_hits(input, b * tune::kBlock,
                                   std::min((b + 1) * tune::kBlock, count), query);
        for (auto& th : pool) th.join();
    }

    // ---- 排他前缀和：命中数 -> 输出起始位置 ----
    std::size_t running = 0;
    for (std::size_t b = 0; b < nblocks; ++b) {
        const std::size_t hits = starts[b];
        starts[b] = running;
        running  += hits;
    }
    starts[nblocks] = running;

    // ---- 第二遍：写出 ----
    if (nt <= 1) {
        write_blocks(input, 0, nblocks, count, output, starts.data(), query);
    } else {
        std::vector<std::thread> pool;
        pool.reserve(nt - 1);
        for (std::size_t t = 1; t < nt; ++t)
            pool.emplace_back([&, t] {
                write_blocks(input, bound(t), bound(t + 1), count, output, starts.data(), query);
            });
        write_blocks(input, bound(0), bound(1), count, output, starts.data(), query);
        for (auto& th : pool) th.join();
    }
    return running;
}

// ============================================================================
//  题目要求的接口（签名与语义不可更改）
//
//  语义：稳定筛选——保持输入顺序、保留全部字段、不去重。
//  返回命中条数；只有 output 的前 N 条是有效结果。
//  count == 0 时允许 input 为空指针（此时直接返回 0，不解引用）。
//  函数内不打印、不读文件、不生成数据、不调用参考实现。
//
//  实现选择：默认单遍方案（本机实测最快）；twopass 为可对比的备选。
//  策略与线程数在计时开始前由 main 设置，函数内只读，因此不引入额外同步开销。
// ============================================================================
static std::atomic<int>      g_strategy{0};   // 0 = 单遍, 1 = 两遍
static std::atomic<unsigned> g_threads{1};

std::size_t filter_records(const Record* input, std::size_t count,
                           Record* output, const Query& query) {
    if (count == 0) return 0;             // 空输入：允许空指针
    if (g_strategy.load(std::memory_order_relaxed) == 1)
        return filter_two_pass(input, count, output, query,
                               g_threads.load(std::memory_order_relaxed));
    return filter_single_pass(input, count, output, query);
}

// ============================================================================
//  外壳：参数解析、输入获取、参考校验、计时、输出
//  与 baseline.cpp 的 main 结构完全一致，仅新增 --impl / --threads 两个选项，
//  并把核心循环换成 filter_records 调用（计时范围因此与 baseline 完全对应）。
// ============================================================================
int main(int argc, char** argv) try {
    std::uint64_t count=100000, max_records=10000000;
    std::uint32_t seed=2026;
    unsigned hit_percent=50, repeats=5;
    unsigned threads=1;
    bool threads_auto=true;
    std::string pattern="random", input_path, output_path, export_path;
    std::string impl="single";
    Query query;
    std::set<std::string> seen;
    for (int i=1; i<argc; ++i) {
        const std::string key=argv[i];
        if (key=="--help") {
            std::cout << "log_filter [--count N | --input FILE] [--hit-percent 0..100]\n"
                      << " [--pattern random|blocks] [--seed U32] [--repeats 1..100]\n"
                      << " [--impl single|twopass] [--threads 1..1024]\n"
                      << " [--begin U64] [--end U64] [--min-latency U32] [--flags U32]\n"
                      << " [--output FILE] [--export-input FILE] [--max-records N]\n"
                      << "Defaults: count=100000 seed=2026 hit=50 repeats=5 max-records=10000000\n"
                      << "          impl=single (threads=1); impl=twopass (threads=cpu count)\n"
                      << "Query: [1000,2000), latency>=100, all bits of flags=3. Decimal arguments.\n";
            return 0;
        }
        if (!seen.insert(key).second || i+1==argc) throw std::runtime_error("duplicate option or missing value");
        const std::string value=argv[++i];
        if (key=="--count") count=number(value);
        else if (key=="--max-records") max_records=number(value);
        else if (key=="--seed") seed=narrow32(number(value));
        else if (key=="--hit-percent") { const auto v=number(value); if(v>100) throw std::runtime_error("invalid hit percent"); hit_percent=static_cast<unsigned>(v); }
        else if (key=="--repeats") { const auto v=number(value); if(v<1 || v>100) throw std::runtime_error("invalid repeats"); repeats=static_cast<unsigned>(v); }
        else if (key=="--threads") { const auto v=number(value); if(v<1 || v>1024) throw std::runtime_error("invalid threads"); threads=static_cast<unsigned>(v); threads_auto=false; }
        else if (key=="--impl") { if(value!="single" && value!="twopass") throw std::runtime_error("invalid impl"); impl=value; }
        else if (key=="--begin") query.begin=number(value);
        else if (key=="--end") query.end=number(value);
        else if (key=="--min-latency") query.min_latency_us=narrow32(number(value));
        else if (key=="--flags") query.required_flags=narrow32(number(value));
        else if (key=="--pattern") pattern=value;
        else if (key=="--input") input_path=value;
        else if (key=="--output") output_path=value;
        else if (key=="--export-input") export_path=value;
        else throw std::runtime_error("unknown option: "+key);
    }
    if (query.begin>query.end || (pattern!="random" && pattern!="blocks")) throw std::runtime_error("invalid query or pattern");
    if (seen.count("--input") && input_path.empty()) throw std::runtime_error("empty input path");
    if ((seen.count("--output") && output_path.empty()) || (seen.count("--export-input") && export_path.empty())) throw std::runtime_error("empty output path");
    if (!input_path.empty() && (seen.count("--count") || seen.count("--seed") || seen.count("--hit-percent") || seen.count("--pattern") || seen.count("--export-input")))
        throw std::runtime_error("input file cannot be combined with generator options");
    if (input_path.empty() && (count>max_records || count>std::numeric_limits<std::size_t>::max()/sizeof(Record)))
        throw std::runtime_error("generated count exceeds limit");

    // 线程数确定：single 方案是串行的，恒为 1；twopass 默认用硬件并发度
    if (impl=="single") { if (threads_auto) threads=1; }
    else if (threads_auto) {
        const unsigned hw=std::thread::hardware_concurrency();
        threads=hw?hw:1u;
    }
    g_strategy.store(impl=="twopass"?1:0, std::memory_order_relaxed);
    g_threads.store(threads, std::memory_order_relaxed);

    // 生成与解码在计时之外（与 baseline 相同）
    auto input=input_path.empty() ? generate(static_cast<std::size_t>(count),hit_percent,pattern,seed) : load(input_path,max_records);
    if (!export_path.empty()) save(export_path,input,input.size());
    auto expected=reference_filter(input,query);
    std::vector<Record> output(input.size());
    std::vector<double> times;
    std::size_t matched=0;
    std::cout << std::setprecision(10)
              << "implementation=" << impl << " threads=" << threads
              << " generator=v1 source=" << (input_path.empty()?"generated":"file")
              << " count=" << input.size() << " sizeof_record=" << sizeof(Record)
              << " seed=" << seed << " pattern=" << pattern << " requested_hit_percent=" << hit_percent
              << " begin=" << query.begin << " end=" << query.end << " min_latency=" << query.min_latency_us
              << " flags=" << query.required_flags << " warmup=1 repeats=" << repeats << '\n';
    for (int run=-1; run<static_cast<int>(repeats); ++run) {
        matched=0;
        const auto start=std::chrono::steady_clock::now();
        // BEGIN CORE: 稳定筛选。计时范围 = 整个 filter_records 调用，
        // 不含生成/加载输入、不含分配 output、不含参考校验与打印 —— 与 baseline 同口径。
        matched=filter_records(input.data(),input.size(),output.data(),query);
        // END CORE: include all output writes, exclude validation and console output.
        const double ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();
        if (matched!=expected.size()) throw std::runtime_error("validation: wrong count");
        for (std::size_t i=0; i<matched; ++i)
            if (!equal_record(output[i],expected[i])) throw std::runtime_error("validation: wrong record/order at "+std::to_string(i));
        if (run>=0) {
            times.push_back(ms);
            std::cout << "sample=" << run << " core_ms=" << ms << " matched=" << matched << " check=PASS\n";
        }
    }
    std::sort(times.begin(),times.end());
    const std::size_t middle=times.size()/2;
    const double median=times.size()%2 ? times[middle] : (times[middle-1]+times[middle])/2;
    std::cout << "median_core_ms=" << median << " actual_hit_percent=" << (input.empty()?0:100.0*matched/input.size()) << " input_Mrecords_per_s=";
    if(median>0) std::cout << input.size()/(median*1000.0);
    else std::cout << "unavailable(timer_resolution)";
    std::cout << '\n';
    if (!output_path.empty()) save(output_path,output,matched);
    return 0;
} catch (const std::exception& e) {
    std::cerr << "error: " << e.what() << '\n';
    return 2;
}
