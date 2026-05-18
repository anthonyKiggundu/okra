#ifndef CONTEXT_TRANSFER_API_IMPL_H_
#define CONTEXT_TRANSFER_API_IMPL_H_

#include <pistache/endpoint.h>
#include <pistache/http.h>
#include <pistache/router.h>
#include <memory>
#include <string>

#include <ContextTransferApi.h>

#include "model/PduSessionContextTransfer.h"
#include "model/UpfResumeRequest.h"
// #include "model/Snssai.h"
#include "../../oai-cn5g-common-src/model/common_model/Snssai.h"
#include "smf_app.hpp"

namespace oai::app::smf {
    class smf_app;
    class smf_pdu_session; // Forward declaration
    struct imported_pdu_context;
}

namespace oai {
namespace smf_server {
namespace api {

class ContextTransferApiImpl : public oai::smf_server::api::ContextTransferApi {
 public:
   void init() override;

  //ContextTransferApiImpl(
  //    std::shared_ptr<Pistache::Rest::Router> router,
  //    oai::app::smf::smf_app* smf_app_inst, std::string address);
  ContextTransferApiImpl(
     std::shared_ptr<Pistache::Rest::Router> router,
     oai::app::smf::smf_app* smf_app_inst, std::string address);

  ~ContextTransferApiImpl() override = default;

  // Original Base Functions
  
  void bind_sm_context(const std::string& supi, const int32_t& pduSessionId, Pistache::Http::ResponseWriter& response) override;
  void export_sm_context(const std::string& supi, const int32_t& pduSessionId, Pistache::Http::ResponseWriter& response) override;
  void import_sm_context(const std::string& supi, const int32_t& pduSessionId, const oai::model::smf::PduSessionContextTransfer& pduSessionContextTransfer, Pistache::Http::ResponseWriter& response) override;
  void pause_sm_context(const std::string& supi, const int32_t& pduSessionId, Pistache::Http::ResponseWriter& response) override;
  void get_sm_context(const std::string &supi, const int32_t &pduSessionId, Pistache::Http::ResponseWriter &response) override;

  // Orchra Novelty Functions (Must match ContextTransferApi.h exactly!)
  void pause_pdu_session(const std::string &imsi, const int32_t &pduSessionId, Pistache::Http::ResponseWriter &response) override;
  void get_pdu_session_context(const std::string &imsi, const int32_t &pduSessionId, Pistache::Http::ResponseWriter &response) override;
  void create_pdu_session_context(const std::string& imsi, const int32_t& pduSessionId, const nlohmann::json& body, Pistache::Http::ResponseWriter& response);
  // void import_pdu_session_context(const std::string &imsi, const int32_t &pduSessionId, const std::string &body, Pistache::Http::ResponseWriter &response) override;
  bool import_pdu_session_context(const oai::app::smf::imported_pdu_context& data, Pistache::Http::ResponseWriter& response) override;
  void bind_pdu_session_context(const std::string &imsi, const int32_t &pduSessionId, Pistache::Http::ResponseWriter &response) override;
  // void resume_pdu_session(const std::string &supi, const int32_t &pduSessionId, const nlohmann::json &body, Pistache::Http::ResponseWriter &response) override;
  void resume_pdu_session(const std::string& supi, const int32_t& pduSessionId, const oai::model::smf::UpfResumeRequest& body, Pistache::Http::ResponseWriter& response) override;
  void release_pdu_context(const std::string &imsi, const int32_t &pduSessionId, Pistache::Http::ResponseWriter &response) override;
  void trigger_migration(const std::string& supi, int target_slice);

  void pause_upf(const std::string& supi, const int32_t& pduSessionId, Pistache::Http::ResponseWriter& response);

 private:
  bool build_transfer_snapshot(
      const std::string& supi, const int32_t& pduSessionId,
      oai::model::smf::PduSessionContextTransfer& out,
      std::string& err) const;

  oai::app::smf::smf_app* m_smf_app;
  std::string m_address;

  // Optional: in-process staging store for imported contexts
  // (If you already have Redis or a DB, you can remove this and store there.)
  std::mutex m_staged_mutex;
  std::string make_key(const std::string& imsi, int32_t id) const { return imsi + "_" + std::to_string(id); }
  // std::map<std::pair<std::string, int32_t>, oai::model::smf::PduSessionContextTransfer> m_staged;
  std::map<std::string, oai::model::smf::PduSessionContextTransfer> m_staged;
};

}  // namespace api
}  // namespace smf_server
}  // namespace oai

#endif
