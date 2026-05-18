#include "Snssai.h" 
#include "../../oai-cn5g-common-src/model/nrf/UPInterfaceType.h"
#include "smf_app.hpp"
#include "ContextTransferApiImpl.hpp"

#include <arpa/inet.h>
#include <netinet/in.h>

#include <atomic>
#include <map>
#include <mutex>
#include <string>
#include <utility>

#include <nlohmann/json.hpp>
#include <pistache/http.h>

#include "itti.hpp"
#include "itti_msg_sbi.hpp"
#include "logger.hpp"
#include "smf_context.hpp"
#include "smf_msg.hpp"

#include "smf_pfcp_association.hpp"
#include "smf_qos_upf_edge.hpp"
#include "model/UpfResumeRequest.h"

#include "smf_procedure.hpp"
#include "conversions.hpp"
#include "smf_config.hpp"

// #include "../../smf_app/orchra_context.hpp"
// #include "../../smf_app/orchra_redis.hpp"
#include "orchra_context.hpp"
#include "orchra_redis.hpp"

#include "../../oai-cn5g-common-src/model/common_model/Snssai.h"
// using Snssai = oai::model::common::Snssai;
#include "../../api-server/model/PduSessionContextTransfer.h"
// #include "../../smf_app/orchra_redis.hpp"

using namespace oai::model::smf;
using namespace oai::smf_server::api;
using namespace oai::model::smf;
using namespace Pistache;

namespace oai {
namespace smf_server {
namespace api {

namespace {

static std::atomic<uint32_t> g_internal_pid{1};

static oai::model::common::Snssai to_openapi_snssai(const snssai_t& s) {
  oai::model::common::Snssai out;
  out.setSst(s.sst);
  // SD is optional; add later once you confirm snssai_t SD representation.
  return out;
}

static void send_json(Pistache::Http::ResponseWriter& response,
                      Pistache::Http::Code code,
                      const nlohmann::json& j) {
  response.headers().add<Pistache::Http::Header::ContentType>(MIME(Application, Json));
  response.send(code, j.dump());
}

static std::string pfcp_node_id_to_string(const pfcp::node_id_t& node_id) {
  // Most deployments use IPv4 node-id
  if (node_id.node_id_type == pfcp::NODE_ID_TYPE_IPV4_ADDRESS) {
    return oai::utils::conv::toString(node_id.u1.ipv4_address);
  }
  // Other types exist (FQDN, IPv6); if you need them, we can extend later.
  return {};
}

static std::shared_ptr<oai::app::smf::pfcp_association> pick_upf_from_edge(
  const std::shared_ptr<oai::app::smf::qos_upf_edge>& edge) {
  if (!edge) return {};
  if (edge->destination_upf) return edge->destination_upf;
  if (edge->source_upf) return edge->source_upf;
  return {};
}

static std::string ipv4_to_string(const in_addr& addr) {
  char buf[INET_ADDRSTRLEN]{0};
  if (!inet_ntop(AF_INET, &addr, buf, sizeof(buf))) return {};
  return std::string(buf);
}

static std::string ipv6_to_string(const in6_addr& addr) {
  char buf[INET6_ADDRSTRLEN]{0};
  if (!inet_ntop(AF_INET6, &addr, buf, sizeof(buf))) return {};
  return std::string(buf);
}

static std::pair<std::string, int32_t> make_key(const std::string& supi, int32_t pid) {
  return {supi, pid};
}

}  // namespace

ContextTransferApiImpl::ContextTransferApiImpl(
    std::shared_ptr<Pistache::Rest::Router> router,
    oai::app::smf::smf_app* smf_app_inst, std::string address)
  : ContextTransferApi(router),
    m_smf_app(smf_app_inst),
    m_address(std::move(address)) {}

void ContextTransferApiImpl::init() {
  ContextTransferApi::init();
}

void ContextTransferApiImpl::trigger_migration(
    const std::string& supi,
    int target_slice) {

  OrchraUeContextSnapshot snap;

  snap.context_id = supi;
  snap.target_slice = target_slice;
  snap.timestamp = std::time(nullptr);

  orchra::export_snapshot_to_redis(snap);

  Logger::smf_app().info("ORCHRA: Migration triggered for SUPI=%s",
                         supi.c_str());
}


bool ContextTransferApiImpl::build_transfer_snapshot(
    const std::string& supi, const int32_t& pduSessionId,
    oai::model::smf::PduSessionContextTransfer& out,
    std::string& err) const {

  if (!m_smf_app) {
    err = "SMF app is null";
    return false;
  }

  auto sc = m_smf_app->supi_2_smf_context(supi);
  if (!sc) {
    err = "SMF context not found for SUPI";
    return false;
  }

  std::shared_ptr<oai::app::smf::smf_pdu_session> sp;
  if (!sc->find_pdu_session((pdu_session_id_t) pduSessionId, sp) || !sp) {
    err = "PDU session not found";
    return false;
  }

  out.setSchemaVersion(1);
  out.setSupi(supi);
  out.setPduSessionId(pduSessionId);

  out.setDnn(sp->get_dnn());
  out.setSnssai(to_openapi_snssai(sp->get_snssai()));

  // UE IP
  if (sp->ipv4) {
    const auto ip = ipv4_to_string(sp->ipv4_address);
    if (!ip.empty()) out.setUeIp(ip);
  } else if (sp->ipv6) {
    const auto ip = ipv6_to_string(sp->ipv6_address);
    if (!ip.empty()) out.setUeIp(ip);
  }

  // TEIDs/SEIDs (SEIDs available immediately)
  // TEIDs/SEIDs
  oai::model::smf::Teids teids;
  teids.setSeidSmf((int64_t) sp->seid);
  teids.setSeidUpf((int64_t) sp->up_fseid.seid);

  // UL/DL TEIDs: derive from QoS flow context (uses pfcp::fteid_t::teid)
  auto sh = sp->get_session_handler();
  
    // UPF association (anchor UPF)
  if (sh) {
    pfcp::qfi_t qfi = sp->default_qfi;
    const auto qfis = sh->get_all_qfis();
    if (!qfis.empty()) qfi = qfis.front();

    const auto qfu = sh->get_qos_flow_context_updated(qfi);
    	
    auto graph = sh->get_session_graph();

    if (graph) {
      const auto access_edges = graph->get_access_edges();
      if (!access_edges.empty()) {
        // Prefer an access edge that matches our chosen qfi, else take first.
        std::shared_ptr<oai::app::smf::qos_upf_edge> chosen_edge = access_edges.front();
        for (const auto& e : access_edges) {
          if (e && (e->qfi == qfi)) {
            chosen_edge = e;
            break;
          }
        }

        auto upf = pick_upf_from_edge(chosen_edge);
        if (upf) {
          oai::model::smf::UpfAssociation upfAssoc;

          // nodeId: readable name (often host or configured name)
          upfAssoc.setNodeId(upf->get_printable_name());

          // n4Addr: derive from PFCP node-id if it's IPv4; fallback to host
          auto n4 = pfcp_node_id_to_string(upf->node_id);
          if (n4.empty()) {
            // fallback: config host (could be FQDN)
            n4 = upf->get_upf_config().get_host();
          }
          if (!n4.empty()) upfAssoc.setN4Addr(n4);

          out.setUpf(upfAssoc);
        }
      }
    }
  }

  out.setTeids(teids);

  // Validate
  try {
    out.validate();
  } catch (const std::exception& e) {
    err = std::string("Snapshot validation failed: ") + e.what();
    return false;
  }

  return true;
}

//Orchra
// implementation of the allowlist check
bool is_authorized(const Pistache::Http::Request& request) {
    auto remote_addr = request.address().host();
    // Logic to check remote_addr against smf_config.internal_api.allow_list
    return true; 
}

void ContextTransferApiImpl::get_sm_context(const std::string &supi, const int32_t &pduSessionId, Pistache::Http::ResponseWriter &response) 
{
    Logger::smf_app().info("Received GET Request for SM Context Transfer. SUPI: %s, PDU ID: %d", supi.c_str(), pduSessionId);

    // 1. Create the Model object (Standardized API response)
    oai::model::smf::PduSessionContextTransfer ctx;
    nlohmann::json j_body;

    // 2. Call the export function we just fixed in smf_app.cpp
    if (m_smf_app->export_pdu_session_context(supi, pduSessionId, j_body)) {
        // Since export_pdu_session_context already gives us valid JSON,
        // we can send it directly.
        response.send(Pistache::Http::Code::Ok, j_body.dump());
    } else {
        response.send(Pistache::Http::Code::Not_Found, "PDU Session Context not found");
    }
}

void ContextTransferApiImpl::export_sm_context(
    const std::string& supi, const int32_t& pduSessionId,
    Pistache::Http::ResponseWriter& response) {

  oai::model::smf::PduSessionContextTransfer out;
  std::string err;
  if (!build_transfer_snapshot(supi, pduSessionId, out, err)) {
    response.send(Pistache::Http::Code::Not_Found, err);
    return;
  }

  nlohmann::json j = out;
  send_json(response, Pistache::Http::Code::Ok, j);
}

/*
void ContextTransferApiImpl::pause_sm_context(
    const std::string& supi, const int32_t& pduSessionId,
    Pistache::Http::ResponseWriter& response) {

  if (!m_smf_app) {
    response.send(Pistache::Http::Code::Internal_Server_Error, "SMF app is null");
    return;
  }

  auto sc = m_smf_app->supi_2_smf_context(supi);
  if (!sc) {
    response.send(Pistache::Http::Code::Not_Found, "SMF context not found for SUPI");
    return;
  }

  std::shared_ptr<oai::app::smf::smf_pdu_session> sp;
  if (!sc->find_pdu_session((pdu_session_id_t) pduSessionId, sp) || !sp) {
    response.send(Pistache::Http::Code::Not_Found, "PDU session not found");
    return;
  }

  // Reuse SMF's existing AN release handler used by upCnxState=DEACTIVATED.
  const uint32_t internal_pid = g_internal_pid.fetch_add(1);

  auto smreq = std::make_shared<itti_sbi_update_sm_context_request>(
      TASK_SMF_SBI, TASK_SMF_APP, internal_pid);

  auto smresp = std::make_shared<itti_sbi_update_sm_context_response>(
      TASK_SMF_APP, TASK_SMF_SBI, internal_pid);

  if (!sc->handle_an_release(smreq, smresp, sp)) {
    response.send(Pistache::Http::Code::Internal_Server_Error, "handle_an_release failed");
    return;
  }

  // Export snapshot after pause
  oai::model::smf::PduSessionContextTransfer out;
  std::string err;
  if (!build_transfer_snapshot(supi, pduSessionId, out, err)) {
    response.send(Pistache::Http::Code::Internal_Server_Error, err);
    return;
  }

  nlohmann::json j = out;
  send_json(response, Pistache::Http::Code::Ok, j);

}
*/

void ContextTransferApiImpl::pause_sm_context(
    const std::string& supi, const int32_t& pduSessionId,
    Pistache::Http::ResponseWriter& response)
{
    // 1) Link to UPF Pause logic first
    // Since pause_upf sends its own error responses, we check if it found the session
    // Or better: call the internal logic of pause_upf directly.

    if (!m_smf_app) {
        response.send(Pistache::Http::Code::Internal_Server_Error, "SMF app is null");
        return;
    }

    auto sc = m_smf_app->supi_2_smf_context(supi);
    if (!sc) {
        response.send(Pistache::Http::Code::Not_Found, "SM context not found");
        return;
    }

    std::shared_ptr<oai::app::smf::smf_pdu_session> sp;
    if (!sc->find_pdu_session((pdu_session_id_t) pduSessionId, sp) || !sp) {
        response.send(Pistache::Http::Code::Not_Found, "PDU session not found");
        return;
    }

    // --- START LINKED UPF PAUSE LOGIC ---
    // This is the code from your pause_upf function
    sp->dl_buffering_paused.store(true);
    Logger::smf_app().info("Pausing UPF: set dl_buffering_paused=1 for SUPI %s", supi.c_str());

    // std::vector<uint8_t> qfis;
    std::vector<pfcp::qfi_s> qfis;
    qfis.push_back(sp->default_qfi); 
 
    // Trigger the N4 change (This tells the UPF to start buffering)
    // Create the procedure object and call the actual OAI function
    // oai::app::smf::session_update_sm_context_procedure proc;
    auto proc = oai::app::smf::session_update_sm_context_procedure(sp);
    if (proc.trigger_n4_modification_for_qfis(qfis) != oai::app::smf::smf_procedure_code::OK) {
        Logger::smf_app().warn("N4 modification failed for IMSI %s", supi.c_str());
    }
    // --- END LINKED UPF PAUSE LOGIC ---

    // 2) Now proceed with the AN Release (Pistache/SBI side)
    const uint32_t internal_pid = g_internal_pid.fetch_add(1);
    auto smreq = std::make_shared<itti_sbi_update_sm_context_request>(TASK_SMF_SBI, TASK_SMF_APP, internal_pid);
    auto smresp = std::make_shared<itti_sbi_update_sm_context_response>(TASK_SMF_APP, TASK_SMF_SBI, internal_pid);

    if (!sc->handle_an_release(smreq, smresp, sp)) {
        response.send(Pistache::Http::Code::Internal_Server_Error, "handle_an_release failed");
        return;
    }

    // 3) Export snapshot
    oai::model::smf::PduSessionContextTransfer out;
    std::string err;
    if (!build_transfer_snapshot(supi, pduSessionId, out, err)) {
        response.send(Pistache::Http::Code::Internal_Server_Error, err);
        return;
    }

    nlohmann::json j = out;
    response.send(Pistache::Http::Code::Ok, j.dump());
}

static void set_n3_next_hop_fteid(
    const std::shared_ptr<oai::app::smf::smf_pdu_session>& sp,
    const pfcp::fteid_t& an_fteid) {

  if (!sp) return;
  auto sh = sp->get_session_handler();
  if (!sh) return;

  auto graph = sh->get_session_graph();
  if (!graph) return;

  std::vector<std::shared_ptr<oai::app::smf::qos_upf_edge>> dl_edges{};
  std::vector<std::shared_ptr<oai::app::smf::qos_upf_edge>> ul_edges{};
  std::shared_ptr<oai::app::smf::pfcp_association> current_upf{};

  graph->dfs_current_upf(dl_edges, ul_edges, current_upf);

//  UPInterfaceType n3_type;
  oai::model::nrf::UPInterfaceType n3_type;
  n3_type.setEnumValue(oai::model::nrf::UPInterfaceType_anyOf::eUPInterfaceType_anyOf::N3);

  for (auto& e : dl_edges) {
    if (e && (e->type == n3_type)) {
      e->next_hop_fteid = an_fteid;
    }
  }
}

/*
static oai::app::smf::smf_procedure_code trigger_n4_modification_all(
    const std::shared_ptr<oai::app::smf::smf_pdu_session>& sp) {

  if (!sp) return oai::app::smf::smf_procedure_code::ERROR;

  // Note: session_update_sm_context_procedure ctor takes non-const shared_ptr&
  auto sp_nc = const_cast<std::shared_ptr<oai::app::smf::smf_pdu_session>&>(sp);
  oai::app::smf::session_update_sm_context_procedure proc(sp_nc);

  std::vector<pfcp::qfi_t> qfis{};  // empty => all edges (per send_n4_session_modification_request)
  return proc.trigger_n4_modification_for_qfis(qfis);
}
*/

static oai::app::smf::smf_procedure_code trigger_n4_modification_all(
    const std::shared_ptr<oai::app::smf::smf_pdu_session>& sp)
{
    if (!sp) {
        Logger::smf_app().error("trigger_n4_modification_all: PDU session pointer is null");
        return oai::app::smf::smf_procedure_code::ERROR;
    }

    // 1. Remove the const_cast reference hack.
    // Just create a new shared_ptr from the existing one.
    // This is thread-safe and incrementing the ref count is cheap.
    std::shared_ptr<oai::app::smf::smf_pdu_session> sp_non_const = sp;

    // 2. Instantiate the procedure.
    // In OAI, this procedure manages the state machine for N4 (PFCP) interactions.
    oai::app::smf::session_update_sm_context_procedure proc(sp_non_const);

    // 3. Prepare the QFI list.
    // An empty list tells the SMF to look up all active QFIs for this session
    // and update their corresponding FARs (Forwarding Action Rules) on the UPF.
    std::vector<pfcp::qfi_t> qfis{};

    Logger::smf_app().debug("Triggering N4 modification for all QFIs to apply pause/buffer state");

    return proc.trigger_n4_modification_for_qfis(qfis);
}

void ContextTransferApiImpl::import_sm_context(
    const std::string& supi, const int32_t& pduSessionId,
    const oai::model::smf::PduSessionContextTransfer& ctx,
    Pistache::Http::ResponseWriter& response) {

  if (ctx.getSchemaVersion() != 1) {
    response.send(Pistache::Http::Code::Bad_Request, "Unsupported schemaVersion");
    return;
  }

  try {
    ctx.validate();
  } catch (const std::exception& e) {
    response.send(Pistache::Http::Code::Bad_Request, std::string("Invalid payload: ") + e.what());
    return;
  }

  {
    std::lock_guard<std::mutex> g(m_staged_mutex);
    m_staged[make_key(supi, pduSessionId)] = ctx;
    // m_staged[{supi, pduSessionId}] = ctx;
  }

  response.send(Pistache::Http::Code::Accepted);
}


void ContextTransferApiImpl::pause_upf(
    const std::string& supi, const int32_t& pduSessionId,
    Pistache::Http::ResponseWriter& response) {

  if (!m_smf_app) {
    response.send(Pistache::Http::Code::Internal_Server_Error, "SMF app is null");
    return;
  }

  auto sc = m_smf_app->supi_2_smf_context(supi);
  if (!sc) {
    response.send(Pistache::Http::Code::Not_Found, "SM context not found");
    return;
  }

  std::shared_ptr<oai::app::smf::smf_pdu_session> sp;
  if (!sc->find_pdu_session((pdu_session_id_t) pduSessionId, sp) || !sp) {
    response.send(Pistache::Http::Code::Not_Found, "PDU session not found");
    return;
  }

  // 1) Mark DL buffering paused (pfcp_create_far will generate apply_action.buff=1 for DL edges)
  sp->dl_buffering_paused.store(true);

  Logger::smf_app().info("pause_upf: set dl_buffering_paused=1 for SUPI %s PSI %d",
                       supi.c_str(), pduSessionId);

  // 2) Trigger N4 Session Modification so UPF actually changes behavior
  const auto rc = trigger_n4_modification_all(sp);
  if (rc != oai::app::smf::smf_procedure_code::OK) {
    response.send(Pistache::Http::Code::Internal_Server_Error,
                  "Failed to trigger N4 session modification");
    return;
  }

  response.send(Pistache::Http::Code::Ok);
}


void ContextTransferApiImpl::resume_pdu_session(
    const std::string& supi, 
    const int32_t& pduSessionId,
    const oai::model::smf::UpfResumeRequest &body,
    Pistache::Http::ResponseWriter& response) {

    // Note: Use the getter methods defined in UpfResumeRequest.h
    uint32_t teid = (uint32_t) body.getAnTeid(); 
    std::string ipv4 = body.getAnIpv4();

    auto sc = m_smf_app->supi_2_smf_context(supi);
    
    if (!sc) {
        response.send(Pistache::Http::Code::Not_Found, "SM context not found");
        return;
    }

    std::shared_ptr<oai::app::smf::smf_pdu_session> sp;
    if (!sc->find_pdu_session((pdu_session_id_t) pduSessionId, sp) || !sp) {
        response.send(Pistache::Http::Code::Not_Found, "PDU session not found");
        return;
    }

    // 1) Disable buffering
    sp->dl_buffering_paused.store(false);

    trigger_n4_modification_all(sp);

    // We pass the parameters from the OpenApi 'body' model to the app logic
    bool success = m_smf_app->resume_pdu_session(supi, (uint32_t)pduSessionId, teid, ipv4);
    //     body.getAnTeid(),
    //    body.getAnIpv4()
    // );

    // 2. END ANCHOR & CALCULATION
    long long duration = 0;
    if (success && sp->is_migrating) {
        auto end_time = std::chrono::steady_clock::now();
        duration = std::chrono::duration_cast<std::chrono::microseconds>(end_time - sp->migration_start_time).count();

        // Log the result once at the very end
        //Logger::smf_app().info("[METRIC_RESULT] PDU_SID: %d | Total_Switch_Overhead: %ld us", pduSessionId, duration);

        sp->is_migrating = false; // Reset
    }

    // 2) Update N3 next_hop_fteid for the new gNB tunnel
    pfcp::fteid_t an_fteid{};
    an_fteid.teid = (uint32_t) body.getAnTeid(); 

    std::string ipv4_str = body.getAnIpv4();
    in_addr addr{};
    //if (inet_pton(AF_INET, body.getAnIpv4().c_str(), &addr) != 1) {
    if (inet_pton(AF_INET, ipv4_str.c_str(), &addr) != 1) {
        response.send(Pistache::Http::Code::Bad_Request, "Invalid anIpv4");
        return;
    }
    an_fteid.ipv4_address = addr;

    // Call the helper (ensure this helper is defined in your .cpp)
    set_n3_next_hop_fteid(sp, an_fteid);

    // 3) Trigger N4 modification to push the new TEID to the UPF
    // const auto rc = smf_app_inst->trigger_n4_modification_all(sp);
    const auto rc = trigger_n4_modification_all(sp);
    if (rc != oai::app::smf::smf_procedure_code::OK) {
        response.send(Pistache::Http::Code::Internal_Server_Error, "Failed N4 modification");
        return;
    }

    if (success) {
        // response.send(Pistache::Http::Code::Ok, "PDU Session Resumed");
	response.send(Pistache::Http::Code::Ok, "PDU Session Resumed and Tunnel Updated");
    } else {
        response.send(Pistache::Http::Code::Internal_Server_Error, "Failed to resume");
    }
    // response.send(Pistache::Http::Code::Ok, "PDU Session Resumed and Tunnel Updated");

    if (duration > 0) {
        Logger::smf_app().info("[METRIC_RESULT] PDU_SID: %d | Total_Switch_Overhead: %lld us",
                               pduSessionId, duration);
    }

}

// Orchra
/*
 *
 * void ContextTransferApiImpl::pause_pdu_session(
    const std::string &imsi,
    const int32_t &pduSessionId,
    Pistache::Http::ResponseWriter &response) 
{
    Logger::smf_app().info("Received Pause request for IMSI %s, PDU ID %d", imsi.c_str(), pduSessionId);

    auto smf_app_inst = oai::app::smf::smf_app::get_instance();
    
    // Assuming you implemented this logic in smf_app.cpp
    bool success = smf_app_inst->pause_pdu_session(imsi, pduSessionId);

    if (success) {
        nlohmann::json j;
        j["imsi"] = imsi;
        j["pdu_session_id"] = pduSessionId;
        j["status"] = "paused";
        
        response.send(Pistache::Http::Code::Ok, j.dump());
    } else {
        response.send(Pistache::Http::Code::Not_Found, "Session not found or already paused");
    }
}
*/

void ContextTransferApiImpl::pause_pdu_session(
    const std::string &imsi,
    const int32_t &pduSessionId,
    Pistache::Http::ResponseWriter &response)
{
    Logger::smf_app().info("Received Pause request (Orchra) for IMSI %s, PDU ID %d", imsi.c_str(), pduSessionId);

    if (!m_smf_app) {
        response.send(Pistache::Http::Code::Internal_Server_Error, "SMF app instance is null");
        return;
    }

    // 1. Get the SMF Context using the SUPI/IMSI
    auto sc = m_smf_app->supi_2_smf_context(imsi);
    if (!sc) {
        Logger::smf_app().warn("Pause failed: SM context not found for IMSI %s", imsi.c_str());
        response.send(Pistache::Http::Code::Not_Found, "IMSI not found");
        return;
    }

    // 2. Find the specific PDU Session
    std::shared_ptr<oai::app::smf::smf_pdu_session> sp;
    if (!sc->find_pdu_session((pdu_session_id_t) pduSessionId, sp) || !sp) {
        Logger::smf_app().warn("Pause failed: PDU session %d not found for IMSI %s", pduSessionId, imsi.c_str());
        response.send(Pistache::Http::Code::Not_Found, "PDU Session not found");
        return;
    }

    // START ANCHOR TO MEASURE THE SWITCHING OVERHEAD
    sp->migration_start_time = std::chrono::steady_clock::now();
    sp->is_migrating = true;

    // 3. Perform the actual "Pause" logic (N4 Modification)
    // We set the buffering flag and trigger N4 modification directly
    sp->dl_buffering_paused.store(true);

    // This triggers the PFCP Session Modification to the UPF
    auto rc = trigger_n4_modification_all(sp);

    if (rc == oai::app::smf::smf_procedure_code::OK) {
        nlohmann::json j;
        j["imsi"] = imsi;
        j["pdu_session_id"] = pduSessionId;
        j["status"] = "paused";
        j["cause"] = "UPF_DL_BUFFERING_ACTIVATED";

        response.send(Pistache::Http::Code::Ok, j.dump());
    } else {
        Logger::smf_app().error("Failed to update UPF for IMSI %s", imsi.c_str());
        response.send(Pistache::Http::Code::Internal_Server_Error, "Failed to update UPF/N4");
    }
}

void ContextTransferApiImpl::bind_sm_context(const std::string& supi, const int32_t& pduSessionId, Pistache::Http::ResponseWriter& response) 
{
    Logger::smf_app().info("Received BIND request for SUPI %s, PDU ID %d", supi.c_str(), pduSessionId);

    // 1. Check if we actually have the data staged
    oai::model::smf::PduSessionContextTransfer ctx;
    {
        std::lock_guard<std::mutex> g(m_staged_mutex);
        auto it = m_staged.find(make_key(supi, pduSessionId));
        if (it == m_staged.end()) {
            response.send(Pistache::Http::Code::Not_Found, "No staged context found for bind. Did you call import first?");
            return;
        }
        ctx = it->second;
    }

    // 2. Actually program the UPF (The logic from function 1)
    // auto smf_app_inst = oai::app::smf::smf_app::get_instance();
    
    // This function must rehydrate the 'ctx' into a real SMF session and push N4 to UPF
    bool success = m_smf_app->bind_pdu_session_to_upf(supi, pduSessionId);

    if (success) {
        // 3. Clean up the staged map after successful bind
        {
            std::lock_guard<std::mutex> g(m_staged_mutex);
            m_staged.erase(make_key(supi, pduSessionId));
        }
        response.send(Pistache::Http::Code::Ok, "Target UPF Programmed and Session Bound Successfully");
    } else {
        response.send(Pistache::Http::Code::Internal_Server_Error, "UPF Programming/N4 Transaction Failed");
    }
}

// Orchra

void ContextTransferApiImpl::get_pdu_session_context(
    const std::string &imsi,
    const int32_t &pduSessionId,
    Pistache::Http::ResponseWriter &response)
{
    // auto smf_app_inst = smf_app::get_instance();

    nlohmann::json ctx;
    if (m_smf_app->export_pdu_session_context(imsi, pduSessionId, ctx)) {
        response.send(Pistache::Http::Code::Ok, ctx.dump());
    } else {
        response.send(Pistache::Http::Code::Not_Found, "Not found");
    }
}


void ContextTransferApiImpl::create_pdu_session_context(
    const std::string &imsi,
    const int32_t &pduSessionId,
    const nlohmann::json &body,
    Pistache::Http::ResponseWriter &response)
{
    auto start_target = std::chrono::steady_clock::now();

    try {
        // 1. Map JSON body to our internal struct
        oai::app::smf::imported_pdu_context data = {};

        data.supi           = imsi;
        data.pdu_session_id = static_cast<uint32_t>(pduSessionId);

        // Extract fields from JSON (ensure keys match what your Redis/Source SMF sends)
        data.dnn         = body.value("dnn", "");
        data.ue_ip       = body.value("ue_ip", "");
        data.upf_node_id = body.value("upf_node_id", "");
        data.upf_addr    = body.value("upf_addr", "");
        data.seid_upf    = body.value("seid_upf", 0UL);
        data.seid_smf    = body.value("seid_smf", 0UL);
        data.amf_uri     = body.value("amf_uri", "");

        // S-NSSAI handling (Assuming source SMF sends it as a sub-object)
        if (body.contains("snssai")) {
            data.snssai.setSst(body["snssai"].value("sst", 0));
            data.snssai.setSd(body["snssai"].value("sd", ""));
        }

        // QoS Rules handling
        if (body.contains("qos_rules") && body["qos_rules"].is_array()) {
            for (auto& rule_json : body["qos_rules"]) {
                oai::app::smf::ImportedQosRule qrd = {};
                qrd.qfi = rule_json.value("qfi", 0);
                // Note: Full oai::nas::QosRule reconstruction from JSON
                // requires more specific parsing depending on your serialization
                data.qos_rules.push_back(qrd);
            }
        }

        // 2. Call the single-argument function
        if (m_smf_app->import_pdu_session_context(data, response)) {

            // Note: If you renamed bind_pdu_session_to_upf to
            // commit_pdu_session_context_async in our previous steps, update this:
            if (m_smf_app->bind_pdu_session_to_upf(imsi, pduSessionId)) {

                auto end_target = std::chrono::steady_clock::now();
                auto duration = std::chrono::duration_cast<std::chrono::microseconds>(end_target - start_target).count();

                Logger::smf_app().info("[BENCHMARK] IMSI: %s | PHASE: TARGET_TOTAL_COMPLETED | Duration: %ld us",
                    imsi.c_str(), duration);

                response.send(Pistache::Http::Code::Created, "Inter-Slice Migration Complete");
            } else {
                response.send(Pistache::Http::Code::Internal_Server_Error, "Imported, but UPF Bind failed");
            }
        } else {
            response.send(Pistache::Http::Code::Bad_Request, "Import failed: Logic error");
        }

    } catch (const nlohmann::json::exception& e) {
        Logger::smf_app().error("JSON Parsing failed: %s", e.what());
        response.send(Pistache::Http::Code::Bad_Request, "Malformed JSON body");
    }
}

/*
void ContextTransferApiImpl::create_pdu_session_context(
    const std::string &imsi,
    const int32_t &pduSessionId,
    const nlohmann::json &body,
    Pistache::Http::ResponseWriter &response)
{
    // Start timing the 'Target Processing' phase (Import + Bind)
    auto start_target = std::chrono::steady_clock::now();

    // 1. Parse JSON and stage the data
    if (m_smf_app->import_pdu_session_context(imsi, pduSessionId, body)) {

        // 2. Program the UPF and link the session
        if (m_smf_app->bind_pdu_session_to_upf(imsi, pduSessionId)) {

            auto end_target = std::chrono::steady_clock::now();
            auto duration = std::chrono::duration_cast<std::chrono::microseconds>(end_target - start_target).count();

            // Log the total time spent on the target SMF for this migration
            Logger::smf_app().info("[BENCHMARK] TYPE: INTER_SLICE | IMSI: %s | PHASE: TARGET_TOTAL_COMPLETED | TS: %ld | Duration: %ld us",
                imsi.c_str(),
                std::chrono::system_clock::now().time_since_epoch().count(), // Use system_clock for wall-clock TS
                duration);

            // Send SUCCESS (Only once!)
            response.send(Pistache::Http::Code::Created, "Inter-Slice Migration Complete");

        } else {
            Logger::smf_app().error("Migration failed at Bind phase for IMSI %s", imsi.c_str());
            response.send(Pistache::Http::Code::Internal_Server_Error, "Context staged, but UPF Bind failed");
        }
    } else {
        Logger::smf_app().error("Migration failed at Import phase for IMSI %s", imsi.c_str());
        response.send(Pistache::Http::Code::Bad_Request, "Import failed: Invalid JSON or state");
    }
}
*/

void ContextTransferApiImpl::release_pdu_context(
    const std::string &imsi,
    const int32_t &pduSessionId,
    Pistache::Http::ResponseWriter &response)
{
    // auto smf = oai::smf::smf_app::get_instance();

    if (m_smf_app->release_pdu_session(imsi, pduSessionId)) {
        response.send(Pistache::Http::Code::Ok, "Released");
    } else {
        response.send(Pistache::Http::Code::Not_Found, "Not found");
    }
}

void ContextTransferApiImpl::bind_pdu_session_context(
    const std::string &supi,
    const int32_t &pduSessionId,
    Pistache::Http::ResponseWriter &response)
{
    Logger::smf_app().info("Received BIND request for SUPI %s, PDU ID %d",
                           supi.c_str(), pduSessionId);

    // 1. Get the pointer to the smf_app (passed during init)
    // We call the complex logic we defined earlier
    bool success = m_smf_app->bind_pdu_session_to_upf(supi, pduSessionId);

    if (success) {
        // 200 OK signals to the orchestrator that UPF-B is programmed
        // and the gNB N2 update is in flight.
        response.send(Pistache::Http::Code::Ok, "PDU Session Bind Successful");
    } else {
        response.send(Pistache::Http::Code::Internal_Server_Error, "Bind failed: Check SMF logs");
    }
}

bool ContextTransferApiImpl::import_pdu_session_context(
    const oai::app::smf::imported_pdu_context& data, 
    Pistache::Http::ResponseWriter& response) 
{
    // This is a stub to satisfy the pure virtual requirement.
    // The actual logic is handled in create_pdu_session_context.
    return true; 
}


}  // namespace api
}  // namespace smf_server
}  // namespace oai
