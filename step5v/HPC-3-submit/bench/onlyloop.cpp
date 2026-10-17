// 只含交付版核心循环（默认单遍无分支），单独一个翻译单元，便于读向量化报告
#include "support.hpp"
std::size_t only_loop(const Record* input, std::size_t count, Record* output, const Query& query) {
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
