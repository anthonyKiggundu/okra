#pragma once

#include <string>
#include <optional>
#include "orchra_context.hpp"

//bool export_snapshot_to_redis(const OrchraUeContextSnapshot& snap);
//std::optional<OrchraUeContextSnapshot> import_snapshot_from_redis(const std::string& context_id);

namespace orchra {
    void init_redis(const std::string& url);
    bool export_snapshot_to_redis(const OrchraUeContextSnapshot& snap);
    std::optional<OrchraUeContextSnapshot> import_snapshot_from_redis(const std::string& supi);
}

