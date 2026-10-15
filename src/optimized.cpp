// optimized.cpp —— 第三关：日志稳定筛选优化
// 编译：g++ -O2 -std=c++17 -pthread src/optimized.cpp -I src -o bench/optimized

#include "support.hpp"   // 平台提供的：Record 结构、Query 结构、生成器、读写文件

#include <algorithm>     // 下面要用 std::min
#include <chrono>        // main 里计时用
#include <cstddef>       // std::size_t
#include <iomanip>       // main 里控制打印精度
#include <iostream>      // main 里打印
#include <set>           // main 里检查重复选项
#include <vector>        // std::vector

// 可调参数（只影响速度，不影响结果）
namespace tune {
// 把输入切成多大的块。4096 条 × 24 字节 = 96 KB。
// 改大改小结果都一样，只是速度会变。
constexpr std::size_t kBlock = 1u << 12;
}

// 判断"这一条记录要不要留下"。
// 四个条件全满足才返回 true：时间戳在区间内、延迟达标、flags 含要求的位。
// 注意：必须写在 filter_records 前面，因为 C++ 要求"先定义后使用"。
inline bool record_matches(const Record& r, const Query& q) noexcept {
    // 时间戳不能早于起点，也不能等于/晚于终点（终点是开区间）
    return r.timestamp >= q.begin && r.timestamp < q.end &&
           // 延迟不能太小
           r.latency_us >= q.min_latency_us &&
           // flags 里要求的位必须全都有
           (r.flags & q.required_flags) == q.required_flags;
}

// ============================================================
// 稳定筛选：把命中的记录按原来的先后顺序复制到 output
// 返回命中的条数；只有 output 的前 N 条是有效结果
// ============================================================
std::size_t filter_records(const Record* input, std::size_t count,
                           Record* output, const Query& query) {
    // 空输入：直接返回 0（题目允许此时 input 是空指针）
    if (count == 0) return 0;

    // 一共要切几块？向上取整。1000 条 ÷ 4096 = 1 块
    const std::size_t nblocks = (count + tune::kBlock - 1) / tune::kBlock;

    // 开一个数组，每块一个格子，最后多留一格存总数
    // 1000 万条数据下也只有约 2442 格，非常小
    std::vector<std::size_t> counts(nblocks + 1, 0);

    // ===== 第一遍：只数，不写 =====
    for (std::size_t b = 0; b < nblocks; ++b) {
        const std::size_t from = b * tune::kBlock;                    // 这块从第几条开始
        const std::size_t to   = std::min(from + tune::kBlock, count); // 到第几条结束
        std::size_t hits = 0;                                          // 本块命中数
        for (std::size_t i = from; i < to; ++i)                        // 逐条扫
            if (record_matches(input[i], query)) ++hits;               // 命中就加一
        counts[b] = hits;                                              // 记下本块有几条
    }

    // ===== 前缀和：把"命中数"就地换成"该从 output 的第几个位置开始写" =====
    std::size_t running = 0;                    // 到目前为止一共命中多少条
    for (std::size_t b = 0; b < nblocks; ++b) {
        const std::size_t hits = counts[b];     // 先取出本块的命中数
        counts[b] = running;                    // 把这一格改写成"本块的写出起点"
        running  += hits;                       // 累加，给下一块用
    }
    counts[nblocks] = running;                  // 最后一格存总数

    // ===== 第二遍：按块起点写出去，块内保持原来的顺序 =====
    for (std::size_t b = 0; b < nblocks; ++b) {
        const std::size_t from = b * tune::kBlock;                    // 同上的起点
        const std::size_t to   = std::min(from + tune::kBlock, count); // 同上的终点
        Record* w = output + counts[b];                               // 本块的写出位置
        for (std::size_t i = from; i < to; ++i) {                     // 块内按顺序扫
            const Record& r = input[i];                               // 读一条
            if (record_matches(r, query)) *w++ = r;                   // 命中就写，指针后移
        }
    }

    // 返回命中总数（等于 counts[nblocks]）
    return running;
}
int main(int argc, char** argv) try {
    std::uint64_t count=100000, max_records=10000000;
    std::uint32_t seed=2026;
    unsigned hit_percent=50, repeats=5;
    std::string pattern="random", input_path, output_path, export_path;
    Query query;
    std::set<std::string> seen;
    for (int i=1; i<argc; ++i) {
        const std::string key=argv[i];
        if (key=="--help") {
            std::cout << "log_filter [--count N | --input FILE] [--hit-percent 0..100]\n"
                      << " [--pattern random|blocks] [--seed U32] [--repeats 1..100]\n"
                      << " [--begin U64] [--end U64] [--min-latency U32] [--flags U32]\n"
                      << " [--output FILE] [--export-input FILE] [--max-records N]\n"
                      << "Defaults: count=100000 seed=2026 hit=50 repeats=5 max-records=10000000\n"
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
    // Generation and file decoding are deliberately outside core timing.
    auto input=input_path.empty() ? generate(static_cast<std::size_t>(count),hit_percent,pattern,seed) : load(input_path,max_records);
    if (!export_path.empty()) save(export_path,input,input.size());
    auto expected=reference_filter(input,query);
    std::vector<Record> output(input.size());
    std::vector<double> times;
    std::size_t matched=0;
    std::cout << std::setprecision(10)
              << "implementation=block-prefix-sum threads=1 generator=v1 source=" << (input_path.empty()?"generated":"file")
              << " count=" << input.size() << " sizeof_record=" << sizeof(Record)
              << " seed=" << seed << " pattern=" << pattern << " requested_hit_percent=" << hit_percent
              << " begin=" << query.begin << " end=" << query.end << " min_latency=" << query.min_latency_us
              << " flags=" << query.required_flags << " warmup=1 repeats=" << repeats << '\n';
    for (int run=-1; run<static_cast<int>(repeats); ++run) {
        matched=0;
        const auto start=std::chrono::steady_clock::now();
        // BEGIN CORE: 稳定筛选（计时范围 = 整个 filter_records 调用，与 baseline 同口径）
        matched = filter_records(input.data(), input.size(), output.data(), query);
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
    // Serialize only the final validated result. File writing is NOT core timing.
    if (!output_path.empty()) save(output_path,output,matched);
    return 0;
} catch (const std::exception& e) {
    std::cerr << "error: " << e.what() << '\n';
    return 2;
}
