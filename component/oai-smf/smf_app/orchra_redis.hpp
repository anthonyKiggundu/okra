#pragma once

#include <string>
#include <optional>
#include "orchra_context.hpp"

//bool export_snapshot_to_redis(const OrchraUeContextSnapshot& snap);
//std::optional<OrchraUeContextSnapshot> import_snapshot_from_redis(const std::string& context_id);

namespace orchra {
    struct RedisCryptoConfig {
        bool enabled{false};
        std::string provider{"aes-gcm"};
        std::string active_kid{"k1"};
        std::string keyring_json{};
        std::string aad{"okra:redis:context:v1"};
        bool plaintext_fallback{true};
        bool dual_write_plaintext{true};
        bool write_encrypted_shadow{true};
        int ttl_seconds{120};
    };

    void init_redis(const std::string& url);
    void init_redis(const std::string& url, const RedisCryptoConfig& cfg);

    bool export_snapshot_to_redis(const OrchraUeContextSnapshot& snap);
    std::optional<OrchraUeContextSnapshot> import_snapshot_from_redis(const std::string& supi);

    bool export_snapshot_to_redis_encrypted(const OrchraUeContextSnapshot& snap);
    std::optional<OrchraUeContextSnapshot> import_snapshot_from_redis_compat(const std::string& supi);
}
