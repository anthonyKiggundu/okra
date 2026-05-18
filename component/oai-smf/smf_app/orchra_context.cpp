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
    {"k_amf", s.k_amf},

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
  s.k_amf         = j.value("k_amf", "");

  s.upf_node_id = j.value("upf_node_id", "");
  s.upf_n4_addr = j.value("upf_n4_addr", "");
  s.upf_seid = j.value("upf_seid", 0ull);
  s.upf_teid = j.value("upf_teid", 0u);
}

OrchraUeContextSnapshot snapshot_from_smf_context(
    std::shared_ptr<oai::app::smf::smf_context> ctx) {
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
  }

  // These are not publicly exposed in your tree; keep them empty/zero.
  s.trace_id = {};
  s.upf_node_id = {};
  s.upf_n4_addr = {};
  //s.upf_seid = 0;
  //s.upf_teid = 0;
   s.upf_seid = session->up_fseid.seid;
   s.upf_teid = session->up_fseid.teid;
   s.upf_n4_addr = ipv4_to_string(session->up_fseid.ipv4_address);

  s.kseaf = kseaf_hex;
  s.kamf = kamf_hex;

  Logger::smf_app().info(
      "ORCHRA: Snapshot created for SUPI %s PDU %u",
      s.supi.c_str(), s.pdu_session_id);

  return s;
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

/*
void apply_snapshot_to_smf_context(const OrchraUeContextSnapshot& s, 
                                   std::shared_ptr<oai::app::smf::smf_context> ctx) {
    
    // 1. Locate the existing session
    auto session = ctx->get_session_ptr(s.pdu_session_id);
    if (!session) {
        Logger::smf_app().error("ORCHRA: Cannot apply snapshot, session %u not found", s.pdu_session_id);
        return;
    }

    // 2. Apply Basic Data
    session->set_dnn(s.dnn);
    session->set_snssai(s.sst, s.sd);

    // 3. Apply IPv4 (String to struct in_addr)
    struct in_addr addr;
    if (inet_aton(s.ip.c_str(), &addr)) {
        session->set_ipv4_address(addr);
    }

    // 4. Apply UPF Connection Data
    // Note: This only updates the SMF memory. It does NOT send an N4 message to the UPF.
    pfcp::fseid_t fseid = {};
    fseid.v4 = 1;    
    fseid.seid = s.upf_seid;
    // For simplicity, we assume the UPF IP in the FSEID is the one from the snapshot
    inet_aton(s.upf_n4_addr.c_str(), &fseid.ipv4_address);
    
    session->set_upf_fseid(fseid);

    Logger::smf_app().info("ORCHRA: Successfully forced snapshot into SUPI %s", s.supi.c_str());
}
*/
