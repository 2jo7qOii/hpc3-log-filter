// 只含平台 baseline 的核心循环（四段短路分支）
#include "support.hpp"
std::size_t base_loop(const Record* input, std::size_t count, Record* output, const Query& query) {
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
