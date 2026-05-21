#include "orchra_context.hpp"
#include "smf_context.hpp"
#include "logger.hpp"
#include <arpa/inet.h> 

#include <map>
#include <sstream>

using namespace oai::app::smf;

using json = nlohmann::json;

static std::string ipv4_to_string(const struct in_addr& addr) {
  char buf[INET_ADDRSTRLEN] = {};
  if (inet_ntop(AF_INET, &addr, buf, sizeof(buf)) == nullptr) {
    return {};
  }
  return std::string(buf);
}

static bool string_to_ipv4(const std::string& ip, struct in_addr& out) {
  return inet_pton(AF_INET, ip.c_str(), &out) == 1;
}

void to_json(json& j, const OrchraUeContextSnapshot& s) {
  j = json{
    {"context_id", s.context_id},
    {"trace_id", s.trace_id},
    {"supi", s.supi},
    {"timestamp", s.timestamp},
    {"pdu_session_id", s.pdu_session_id},
    {"dnn", s.dnn},
    {"sst", s.sst},
    {"sd", s.sd},
    {"ip", s.ip},
    // New Security/NAS state
    {"dl_nas_count", s.dl_nas_count},
    {"ul_nas_count", s.ul_nas_count},
    {"kamf", s.kamf},
    {"vector_pointer", s.vector_pointer},
    {"kseaf", s.kseaf},
    {"ran_ue_ngap_id", s.ran_ue_ngap_id},

    {"upf_node_id", s.upf_node_id},
    {"upf_n4_addr", s.upf_n4_addr},
    {"upf_seid", s.upf_seid},
    {"upf_teid", s.upf_teid}
  };
}

void from_json(const nlohmann::json& j, OrchraUeContextSnapshot& s) {
  s.context_id = j.value("context_id", "");
  s.trace_id = j.value("trace_id", "");
  s.supi = j.value("supi", "");
  s.timestamp = j.value("timestamp", 0u);
  s.pdu_session_id = j.value("pdu_session_id", 0u);
  s.dnn = j.value("dnn", "");
  s.sst = j.value("sst", 0u);
  s.sd = j.value("sd", "");
  s.ip = j.value("ip", "");

  // New Security/NAS state (with safe defaults)
  s.dl_nas_count   = j.value("dl_nas_count", 0u);
  s.ul_nas_count   = j.value("ul_nas_count", 0u);
  s.kamf         = j.value("kamf", "");
  s.vector_pointer = j.value("vector_pointer", 0u);
  s.kseaf          = j.value("kseaf", "");
  s.ran_ue_ngap_id = j.value("ran_ue_ngap_id", 0ull);

  s.upf_node_id = j.value("upf_node_id", "");
  s.upf_n4_addr = j.value("upf_n4_addr", "");
  s.upf_seid = j.value("upf_seid", 0ull);
  s.upf_teid = j.value("upf_teid", 0u);
}

OrchraUeContextSnapshot snapshot_from_smf_context(
    std::shared_ptr<oai::app::smf::smf_context> ctx,
    const std::string& kseaf_hex, const std::string& kamf_hex ) {
  OrchraUeContextSnapshot s{};

  if (!ctx) {
    return s;
  }

  s.supi = ctx->get_supi();

  std::map<pdu_session_id_t, std::shared_ptr<oai::app::smf::smf_pdu_session>>
      sessions;
  ctx->get_pdu_sessions(sessions);

  if (sessions.empty()) {
    Logger::smf_app().warn(
        "ORCHRA: no PDU sessions found for SUPI %s", s.supi.c_str());
    s.context_id = s.supi;
    return s;
  }

  const auto& [pdu_id, session] = *sessions.begin();
  s.pdu_session_id = pdu_id;
  s.context_id = s.supi + "-" + std::to_string(s.pdu_session_id);

  if (session) {
    s.dnn = session->get_dnn();

    const auto snssai = session->get_snssai();
    s.sst = static_cast<uint8_t>(snssai.sst);
    s.sd = snssai.sd;

    struct in_addr ue_ipv4 = session->ipv4_address;
    // s.ip = ipv4_to_string(ue_ipv4);
    s.ip = inet_ntoa(ue_ipv4);

    s.upf_seid = session->up_fseid.seid;
    s.upf_teid = session->up_fseid.teid;
    s.upf_n4_addr = ipv4_to_string(session->up_fseid.ipv4_address);

  }

  // These are not publicly exposed in your tree; keep them empty/zero.
  //s.trace_id = {};
  //s.upf_node_id = {};
  //s.upf_n4_addr = {};
  //s.upf_seid = 0;
  //s.upf_teid = 0;

  s.kseaf = kseaf_hex;
  s.kamf = kamf_hex;

  Logger::smf_app().info(
      "ORCHRA: Snapshot created for SUPI %s PDU %u",
      s.supi.c_str(), s.pdu_session_id);

  return s;
}

OrchraUeContextSnapshot snapshot_from_nas_context(
    std::shared_ptr<nas_context> ctx,
    const std::string& kseaf_hex,
    const std::string& kamf_hex) 
{
    OrchraUeContextSnapshot snap{};
    if (!ctx) {
        return snap;
    }

    // 1. Populate basic subscriber details
    snap.supi = ctx->supi;
    snap.context_id = ctx->supi; // AMF looks up primarily by SUPI/IMSI

    // 2. Populate Security Context details if initialized
    if (ctx->security_ctx.has_value()) {
        // Reconstruct flat 32-bit integer counters from the split structure format
        snap.ul_nas_count = (ctx->security_ctx->ul_count.overflow << 8) | 
                             ctx->security_ctx->ul_count.seq_num;
        snap.dl_nas_count = (ctx->security_ctx->dl_count.overflow << 8) | 
                             ctx->security_ctx->dl_count.seq_num;
        
        // Retain tracking indices for authentication vectors
        snap.vector_pointer = ctx->security_ctx->vector_pointer;
    } else {
        snap.ul_nas_count = 0;
        snap.dl_nas_count = 0;
        snap.vector_pointer = 0;
    }

    // 3. Unpack and assign generated key parameters passed from the AKA procedure
    snap.kseaf = kseaf_hex;
    snap.kamf  = kamf_hex;

    Logger::amf_n1().info(
        "ORCHRA: NAS Snapshot created for SUPI: %s | UL-NAS: %u | DL-NAS: %u",
        snap.supi.c_str(), snap.ul_nas_count, snap.dl_nas_count
    );

    return snap;
}

void apply_snapshot_to_smf_context(const OrchraUeContextSnapshot& s,
     std::shared_ptr<oai::app::smf::smf_context> ctx,    
     std::string* out_kseaf_hex,
     std::string* out_kamf_hex) {

    if (!ctx) return;

    if (out_kseaf_hex) *out_kseaf_hex = s.kseaf;
    if (out_kamf_hex)  *out_kamf_hex  = s.kamf;

    // Assuming you added get_session_ptr to smf_context as discussed,
    // otherwise use ctx->pdu_sessions[s.pdu_session_id] if pdu_sessions is public.
    auto session = ctx->get_session_ptr(s.pdu_session_id);
    if (!session) {
        Logger::smf_app().error("ORCHRA: Cannot apply snapshot, session %u not found", s.pdu_session_id);
        return;
    }

    // 2. Apply Basic Data (Direct member access)
    session->dnn = s.dnn;
    session->snssai.sst = s.sst;
    // If your snssai.sd is a string, use direct assignment.
    // If it's a 3-byte array or int, conversion may be needed.
    session->snssai.sd = s.sd;

    // 3. Apply IPv4 (Direct member access)
    if (inet_aton(s.ip.c_str(), &session->ipv4_address)) {
        session->ipv4 = true; // Set the boolean flag found in your header
    }

    // 4. Apply UPF Connection Data (Using up_fseid member from your header)
    // Note: This only updates the SMF memory.
    session->up_fseid.v4 = 1; // Presence flag found in your hash function
    session->up_fseid.v6 = 0;
    session->up_fseid.seid = s.upf_seid;

    if (inet_aton(s.upf_n4_addr.c_str(), &session->up_fseid.ipv4_address) == 0) {
        Logger::smf_app().error("ORCHRA: Invalid UPF N4 address in snapshot: %s", s.upf_n4_addr.c_str());
    }

    // Also update the session-level SEID if used by your version's lookup logic
    session->seid = s.upf_seid;

    Logger::smf_app().info("ORCHRA: Successfully forced snapshot into session %u for SUPI %s",
                            s.pdu_session_id, s.supi.c_str());
}

