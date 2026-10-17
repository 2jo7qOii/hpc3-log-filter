// ============================================================================
//  micro_core.cpp —— 五个变体的核心循环（单独翻译单元，防止跨过程内联/消除）
//
//  变体 1：baseline 原样。四个比较用 && 串成短路链 —— 编译器为每个比较生成一个
//          条件分支（等价于四次 if(...) continue;），是否写出也在分支里。
//  变体 2：变体 1 + 阈值局部化（把 Query 的四个字段先读进局部变量）。
//  变体 3：短路链换成按位与（无条件求值 4 个比较），但"是否写"仍是分支。
//  变体 4：变体 3 + 无条件写 + 掩码推进写指针（当前交付的默认实现）。
//  变体 5：变体 3 + "掩码判断后再写"（无短路，但写出仍靠分支）。
//
//  编译：g++ -O2 -std=c++17 -pthread
// ============================================================================
#include "support.hpp"

// 变体 1：baseline 的原始写法
std::size_t v_baseline(const Record* input, std::size_t count, Record* output, const Query& query) {
    std::size_t m = 0;
    for (std::size_t i = 0; i < count; ++i) {
        const Record& r = input[i];
        if (query.begin <= r.timestamp && r.timestamp < query.end &&
            r.latency_us >= query.min_latency_us &&
            (r.flags & query.required_flags) == query.required_flags) {
            output[m++] = r;
        }
    }
    return m;
}

// 变体 2：只做阈值局部化
std::size_t v_local_thresholds(const Record* input, std::size_t count, Record* output, const Query& query) {
    const std::uint64_t q_begin = query.begin, q_end = query.end;
    const std::uint32_t q_lat = query.min_latency_us, q_flags = query.required_flags;
    std::size_t m = 0;
    for (std::size_t i = 0; i < count; ++i) {
        const Record& r = input[i];
        if (q_begin <= r.timestamp && r.timestamp < q_end &&
            r.latency_us >= q_lat && (r.flags & q_flags) == q_flags) {
            output[m++] = r;
        }
    }
    return m;
}

// 变体 3：按位与求掩码，但写出仍在分支内
std::size_t v_shortcircuit(const Record* input, std::size_t count, Record* output, const Query& query) {
    const std::uint64_t q_begin = query.begin, q_end = query.end;
    const std::uint32_t q_lat = query.min_latency_us, q_flags = query.required_flags;
    std::size_t m = 0;
    for (std::size_t i = 0; i < count; ++i) {
        const Record& r = input[i];
        const unsigned ok = (unsigned)(r.timestamp >= q_begin) & (unsigned)(r.timestamp < q_end)
                          & (unsigned)(r.latency_us >= q_lat)
                          & (unsigned)((r.flags & q_flags) == q_flags);
        if (ok) output[m++] = r;
    }
    return m;
}

// 变体 4：当前交付的默认实现 —— 无条件写、掩码推进
std::size_t v_branchless_cmov(const Record* input, std::size_t count, Record* output, const Query& query) {
    const std::uint64_t q_begin = query.begin, q_end = query.end;
    const std::uint32_t q_lat = query.min_latency_us, q_flags = query.required_flags;
    std::size_t m = 0;
    for (std::size_t i = 0; i < count; ++i) {
        const Record& r = input[i];
        const unsigned ok = (unsigned)(r.timestamp >= q_begin) & (unsigned)(r.timestamp < q_end)
                          & (unsigned)(r.latency_us >= q_lat)
                          & (unsigned)((r.flags & q_flags) == q_flags);
        output[m] = r;
        m += ok;
    }
    return m;
}

// 变体 5：与变体 3 相同语义，但让编译器在"用掩码做条件写"时自行选择 cmov/分支
std::size_t v_branchless_guarded(const Record* input, std::size_t count, Record* output, const Query& query) {
    const std::uint64_t q_begin = query.begin, q_end = query.end;
    const std::uint32_t q_lat = query.min_latency_us, q_flags = query.required_flags;
    std::size_t m = 0;
    for (std::size_t i = 0; i < count; ++i) {
        const Record& r = input[i];
        const unsigned ok = (unsigned)(r.timestamp >= q_begin) & (unsigned)(r.timestamp < q_end)
                          & (unsigned)(r.latency_us >= q_lat)
                          & (unsigned)((r.flags & q_flags) == q_flags);
        output[m] = r;
        m = ok ? m + 1 : m;      // 与变体 4 数值等价，但写成显式选择
    }
    return m;
}
