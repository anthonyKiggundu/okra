#pragma once

#include <string>
#include <memory>
#include <optional>
#include <nlohmann/json.hpp>
#include <ctime>
#include <cstdint>

// Forward declaration (OAI type)
namespace oai {
  namespace app {
    namespace smf {
      class smf_context;
    }
  }
}

class nas_context;

struct OrchraUeContextSnapshot {
  std::string context_id;
  std::string trace_id;

  std::string supi;
  uint32_t pdu_session_id;

  std::string target_slice;
  // std::time_t timestamp;
  int64_t timestamp;

  std::string dnn;
  uint8_t sst;
  std::string sd;

  std::string ip;
  // --- Add these for "Seamless" Security Sync ---
  uint32_t dl_nas_count;     // Downlink NAS Sequence Number
  uint32_t ul_nas_count;     // Uplink NAS Sequence Number
  uint32_t vector_pointer{0};
  std::string kamf;         // Security Anchor Key (Hex string)
  std::string kseaf;   // hex string
  uint64_t ran_ue_ngap_id;
  uint64_t amf_ue_ngap_id;

  int gnb_assoc_id;
  int sctp_stream_recv;
  int sctp_stream_send;
  bool ue_context_request;
  uint8_t ncc;
  
  uint32_t target_ran_ue_ngap_id;
  int target_gnb_assoc_id;

  std::string upf_node_id;
  std::string upf_n4_addr;
  uint64_t upf_seid;
  uint32_t upf_teid;
};

// ---- JSON helpers ----
void to_json(nlohmann::json& j, const OrchraUeContextSnapshot& s);
void from_json(const nlohmann::json& j, OrchraUeContextSnapshot& s);

// ---- Mapping ----
OrchraUeContextSnapshot snapshot_from_smf_context(
      std::shared_ptr<oai::app::smf::smf_context> ctx,
      const std::string& kseaf_hex = {},
      const std::string& kamf_hex = {});

OrchraUeContextSnapshot snapshot_from_nas_context(
    std::shared_ptr<nas_context> ctx,
    const std::string& kseaf_hex = {},
    const std::string& kamf_hex = {});

void apply_snapshot_to_smf_context(
     const OrchraUeContextSnapshot& snap, 
     std::shared_ptr<oai::app::smf::smf_context> ctx,
     std::string* out_kseaf_hex = nullptr,
     std::string* out_kamf_hex = nullptr);
