#include "orchra_redis.hpp"
#include "logger.hpp"
#include <sw/redis++/redis++.h>
#include <memory>

using namespace sw::redis;

// Global redis instance using a connection pool
// static Redis redis("tcp://127.0.0.1:6379");
static std::unique_ptr<Redis> redis_ptr = nullptr;

namespace orchra {

void init_redis(const std::string& url) {
    if (!redis_ptr) {
        redis_ptr = std::make_unique<Redis>(url);
        Logger::smf_app().info("ORCHRA: Redis initialized at %s", url.c_str());
    }
}

bool export_snapshot_to_redis(const OrchraUeContextSnapshot& snap) {
    // Safety check: ensure redis is initialized
    if (!redis_ptr) {
        Logger::smf_app().error("ORCHRA: Cannot export; Redis pointer is null.");
        return false;
    }

    try {
        nlohmann::json j;
        j["supi"]           = snap.supi;
        j["pdu_session_id"] = (int)snap.pdu_session_id;
        j["dnn"]            = snap.dnn;
        j["sst"]            = snap.sst;
        j["sd"]             = snap.sd;
        j["ip"]             = snap.ip;
	j["kseaf"]  	    = snap.kseaf;
        j["kamf"]  	    = snap.kamf;
        j["upf_n4_addr"]    = snap.upf_n4_addr;
        j["upf_seid"]       = snap.upf_seid;

        std::string key = "orchra:ue:" + snap.supi;

        // Use the pointer (->) instead of the dot (.)
        redis_ptr->set(key, j.dump());
        redis_ptr->expire(key, 120);

        Logger::smf_app().info("ORCHRA: Stored snapshot in Redis for SUPI: %s", snap.supi.c_str());
        return true;

    } catch (const Error& e) {
        Logger::smf_app().error("ORCHRA: Redis export failed: %s", e.what());
        return false;
    } catch (const std::exception& e) {
        Logger::smf_app().error("ORCHRA: Redis export failed: %s", e.what());
        return false;
    }

}

std::optional<OrchraUeContextSnapshot> import_snapshot_from_redis(const std::string& supi) {
    if (!redis_ptr) {
        Logger::smf_app().error("ORCHRA: Cannot import; Redis pointer is null.");
        return std::nullopt;
    }

    try {
        std::string key = "orchra:ue:" + supi;

        // Use the pointer (->)
        auto val = redis_ptr->get(key);
        if (!val) {
            Logger::smf_app().warn("ORCHRA: No Redis data for SUPI: %s", supi.c_str());
            return std::nullopt;
        }

        auto j = nlohmann::json::parse(*val);

        OrchraUeContextSnapshot snap;
        snap.supi           = j["supi"].get<std::string>();
        snap.pdu_session_id = (uint8_t)j["pdu_session_id"].get<int>();
        snap.dnn            = j["dnn"].get<std::string>();
        snap.sst            = j["sst"].get<uint8_t>();
        snap.sd             = j["sd"].get<std::string>();
        snap.ip             = j["ip"].get<std::string>();
	snap.kseaf 	    = j["kseaf"].get<std::string>(); //.value("kseaf", "");
        snap.kamf  	    = j["kamf"].get<std::string>(); //.value("kamf", "");
        snap.upf_n4_addr    = j["upf_n4_addr"].get<std::string>();
        snap.upf_seid       = j["upf_seid"].get<uint64_t>();

        Logger::smf_app().info("ORCHRA: Loaded snapshot from Redis for SUPI: %s", supi.c_str());
        return snap;

    } catch (const std::exception& e) {
        Logger::smf_app().error("ORCHRA: Redis import failed: %s", e.what());
        return std::nullopt;
    } catch (const std::exception& e) {
        Logger::smf_app().error("ORCHRA: Redis import failed: %s", e.what());
        return std::nullopt;
    }
}

} // namespace orchra

/*
bool export_snapshot_to_redis(const OrchraUeContextSnapshot& snap) {
    try {
        nlohmann::json j;
        // Map the structure to JSON manually to avoid conversion errors
        j["supi"]           = snap.supi;
        j["pdu_session_id"] = (int)snap.pdu_session_id; // Cast to int for JSON clarity
        j["dnn"]            = snap.dnn;
        j["sst"]            = snap.sst;
        j["sd"]             = snap.sd;
        j["ip"]             = snap.ip;
        j["upf_n4_addr"]    = snap.upf_n4_addr;
        j["upf_seid"]       = snap.upf_seid;

        std::string key = "orchra:ue:" + snap.supi;

        redis.set(key, j.dump());
        redis.expire(key, 120); // TTL 120 seconds

        Logger::smf_app().info("ORCHRA: Stored snapshot in Redis for SUPI: %s", snap.supi.c_str());
        return true;

    } catch (const Error& e) {
        Logger::smf_app().error("ORCHRA: Redis export failed: %s", e.what());
        return false;
    }
}

std::optional<OrchraUeContextSnapshot> import_snapshot_from_redis(const std::string& supi) {
    try {
        std::string key = "orchra:ue:" + supi;

        auto val = redis.get(key);
        if (!val) {
            Logger::smf_app().warn("ORCHRA: No Redis data for SUPI: %s", supi.c_str());
            return std::nullopt;
        }

        auto j = nlohmann::json::parse(*val);

        OrchraUeContextSnapshot snap;
        snap.supi           = j["supi"].get<std::string>();
        snap.pdu_session_id = (uint8_t)j["pdu_session_id"].get<int>();
        snap.dnn            = j["dnn"].get<std::string>();
        snap.sst            = j["sst"].get<uint8_t>();
        snap.sd             = j["sd"].get<std::string>();
        snap.ip             = j["ip"].get<std::string>();
        snap.upf_n4_addr    = j["upf_n4_addr"].get<std::string>();
        snap.upf_seid       = j["upf_seid"].get<uint64_t>();

        Logger::smf_app().info("ORCHRA: Loaded snapshot from Redis for SUPI: %s", supi.c_str());
        return snap;

    } catch (const std::exception& e) {
        Logger::smf_app().error("ORCHRA: Redis import failed: %s", e.what());
        return std::nullopt;
    }
}

} // namespace orchra
*/
