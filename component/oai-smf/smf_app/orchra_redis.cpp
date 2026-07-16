#include "orchra_redis.hpp"
#include "logger.hpp"
#include <sw/redis++/redis++.h>
#include <sw/redis++/errors.h>
#include <memory>
#include <string>
#include <optional>
#include <exception>
#include <unordered_map>
#include <vector>
#include <cstdlib>
#include <openssl/evp.h>
#include <openssl/rand.h>
#include "orchra_context.hpp"
#include <nlohmann/json.hpp>

#define ORCHRA_LOG() Logger::smf_app()
using namespace sw::redis;

// Global redis instance using a connection pool
static std::unique_ptr<Redis> redis_ptr = nullptr;

static orchra::RedisCryptoConfig g_crypto_cfg{};
static std::unordered_map<std::string, std::vector<uint8_t>> g_keyring;
static std::string g_active_kid = "k1";

namespace {
static inline bool valid_aes_key_len(const std::vector<uint8_t>& k) {
  return k.size() == 16 || k.size() == 24 || k.size() == 32;
}

static void log_crypto_mode() {
  ORCHRA_LOG().info(
      "ORCHRA: crypto cfg enabled=%d provider=%s dual_plain=%d shadow=%d ttl=%d active_kid=%s",
      g_crypto_cfg.enabled, g_crypto_cfg.provider.c_str(), g_crypto_cfg.dual_write_plaintext,
      g_crypto_cfg.write_encrypted_shadow, g_crypto_cfg.ttl_seconds, g_active_kid.c_str());
}

static std::string b64url_encode(const std::vector<uint8_t>& in) {
  if (in.empty()) return "";
  const int out_len = 4 * ((int(in.size()) + 2) / 3);
  std::string out(out_len, '\0');
  int real = EVP_EncodeBlock(reinterpret_cast<unsigned char*>(&out[0]), in.data(), (int)in.size());
  out.resize(real > 0 ? (size_t)real : 0);
  for (auto& c : out) {
    if (c == '+') c = '-';
    else if (c == '/') c = '_';
  }
  while (!out.empty() && out.back() == '=') out.pop_back();
  return out;
}

static std::vector<uint8_t> b64url_decode(std::string s) {
  for (auto& c : s) {
    if (c == '-') c = '+';
    else if (c == '_') c = '/';
  }
  while (s.size() % 4) s.push_back('=');
  std::vector<uint8_t> out((s.size() * 3) / 4 + 3);
  int n = EVP_DecodeBlock(out.data(), reinterpret_cast<const unsigned char*>(s.data()), (int)s.size());
  if (n < 0) return {};
  size_t pad = 0;
  if (!s.empty() && s[s.size() - 1] == '=') pad++;
  if (s.size() > 1 && s[s.size() - 2] == '=') pad++;
  out.resize((size_t)n - pad);
  return out;
}

static bool aes_gcm_encrypt(
    const std::vector<uint8_t>& key, const std::vector<uint8_t>& plaintext, const std::string& aad,
    std::vector<uint8_t>& nonce, std::vector<uint8_t>& ciphertext_and_tag) {
  nonce.resize(12);
  if (RAND_bytes(nonce.data(), (int)nonce.size()) != 1) return false;
  EVP_CIPHER_CTX* ctx = EVP_CIPHER_CTX_new();
  if (!ctx) return false;

  bool ok = false;
  int len = 0, out_len = 0;
  ciphertext_and_tag.assign(plaintext.size() + 16, 0);

  const EVP_CIPHER* cipher = nullptr;
  if (key.size() == 16) cipher = EVP_aes_128_gcm();
  else if (key.size() == 24) cipher = EVP_aes_192_gcm();
  else if (key.size() == 32) cipher = EVP_aes_256_gcm();
  else goto done;

  if (EVP_EncryptInit_ex(ctx, cipher, nullptr, nullptr, nullptr) != 1) goto done;
  if (EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_SET_IVLEN, (int)nonce.size(), nullptr) != 1) goto done;
  if (EVP_EncryptInit_ex(ctx, nullptr, nullptr, key.data(), nonce.data()) != 1) goto done;

  if (!aad.empty()) {
    if (EVP_EncryptUpdate(
            ctx, nullptr, &len, reinterpret_cast<const unsigned char*>(aad.data()), (int)aad.size()) != 1)
      goto done;
  }

  if (EVP_EncryptUpdate(ctx, ciphertext_and_tag.data(), &len, plaintext.data(), (int)plaintext.size()) != 1)
    goto done;
  out_len = len;

  if (EVP_EncryptFinal_ex(ctx, ciphertext_and_tag.data() + out_len, &len) != 1) goto done;
  out_len += len;

  ciphertext_and_tag.resize((size_t)out_len + 16);
  if (EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_GET_TAG, 16, ciphertext_and_tag.data() + out_len) != 1) goto done;

  ok = true;

done:
  EVP_CIPHER_CTX_free(ctx);
  return ok;
}

static bool aes_gcm_decrypt(
    const std::vector<uint8_t>& key, const std::vector<uint8_t>& nonce,
    const std::vector<uint8_t>& ciphertext_and_tag, const std::string& aad, std::vector<uint8_t>& plaintext) {
  if (ciphertext_and_tag.size() < 16) return false;

  size_t ct_len = ciphertext_and_tag.size() - 16;
  const unsigned char* tag = ciphertext_and_tag.data() + ct_len;

  EVP_CIPHER_CTX* ctx = EVP_CIPHER_CTX_new();
  if (!ctx) return false;

  bool ok = false;
  int len = 0, out_len = 0;
  plaintext.assign(ct_len, 0);

  const EVP_CIPHER* cipher = nullptr;
  if (key.size() == 16) cipher = EVP_aes_128_gcm();
  else if (key.size() == 24) cipher = EVP_aes_192_gcm();
  else if (key.size() == 32) cipher = EVP_aes_256_gcm();
  else goto done;

  if (EVP_DecryptInit_ex(ctx, cipher, nullptr, nullptr, nullptr) != 1) goto done;
  if (EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_SET_IVLEN, (int)nonce.size(), nullptr) != 1) goto done;
  if (EVP_DecryptInit_ex(ctx, nullptr, nullptr, key.data(), nonce.data()) != 1) goto done;

  if (!aad.empty()) {
    if (EVP_DecryptUpdate(
            ctx, nullptr, &len, reinterpret_cast<const unsigned char*>(aad.data()), (int)aad.size()) != 1)
      goto done;
  }

  if (EVP_DecryptUpdate(ctx, plaintext.data(), &len, ciphertext_and_tag.data(), (int)ct_len) != 1) goto done;
  out_len = len;

  if (EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_SET_TAG, 16, const_cast<unsigned char*>(tag)) != 1) goto done;
  if (EVP_DecryptFinal_ex(ctx, plaintext.data() + out_len, &len) != 1) goto done;
  out_len += len;

  plaintext.resize(out_len);
  ok = true;

done:
  EVP_CIPHER_CTX_free(ctx);
  return ok;
}

static void init_keyring_from_cfg() {
  g_keyring.clear();
  g_active_kid = g_crypto_cfg.active_kid.empty() ? "k1" : g_crypto_cfg.active_kid;

  try {
    if (!g_crypto_cfg.keyring_json.empty()) {
      auto j = nlohmann::json::parse(g_crypto_cfg.keyring_json);
      g_active_kid = j.value("active_kid", g_active_kid);

      if (j.contains("keys") && j["keys"].is_object()) {
        for (auto it = j["keys"].begin(); it != j["keys"].end(); ++it) {
          if (!it.value().is_string()) {
            ORCHRA_LOG().warn("ORCHRA: keyring entry '%s' not a string, skipping", it.key().c_str());
            continue;
          }
          auto raw = b64url_decode(it.value().get<std::string>());
          if (valid_aes_key_len(raw)) {
            g_keyring[it.key()] = raw;
          } else {
            ORCHRA_LOG().warn(
                "ORCHRA: keyring entry '%s' invalid key length=%zu, skipping", it.key().c_str(), raw.size());
          }
        }
      }
    }

    if (g_keyring.empty()) {
      ORCHRA_LOG().warn("ORCHRA: keyring empty after parse");
    }
    if (g_keyring.find(g_active_kid) == g_keyring.end()) {
      ORCHRA_LOG().warn("ORCHRA: active_kid '%s' not found in keyring", g_active_kid.c_str());
    }

  } catch (...) {
    ORCHRA_LOG().error("ORCHRA: keyring parse failed");
  }
}

static bool try_decode_envelope_or_plain(const std::string& raw, nlohmann::json& out_plain_json) {
  auto j = nlohmann::json::parse(raw, nullptr, false);
  if (j.is_discarded()) return false;

  if (!j.contains("_enc")) {
    out_plain_json = j;
    return j.is_object();
  }

  const std::string enc = j.value("_enc", "");
  if (enc == "fernet") {
    ORCHRA_LOG().error("ORCHRA: fernet envelope detected; unsupported in SMF C++ compat patch");
    return false;
  }
  if (enc != "aes-gcm") return false;

  const std::string kid = j.value("_kid", g_active_kid);
  auto it = g_keyring.find(kid);
  if (it == g_keyring.end()) return false;
  if (!valid_aes_key_len(it->second)) {
    ORCHRA_LOG().error("ORCHRA: invalid key length for kid=%s", kid.c_str());
    return false;
  }

  auto nonce = b64url_decode(j.value("nonce", ""));
  auto cttag = b64url_decode(j.value("ciphertext", ""));

  std::vector<uint8_t> plain;
  if (!aes_gcm_decrypt(it->second, nonce, cttag, j.value("_aad", g_crypto_cfg.aad), plain)) return false;

  std::string s(plain.begin(), plain.end());
  auto pj = nlohmann::json::parse(s, nullptr, false);
  if (pj.is_discarded() || !pj.is_object()) return false;

  out_plain_json = pj;
  return true;
}
}  // namespace

namespace orchra {

void init_redis(const std::string& url) {
  RedisCryptoConfig cfg{};
  cfg.enabled = false;
  init_redis(url, cfg);
}

void init_redis(const std::string& url, const RedisCryptoConfig& cfg) {
  g_crypto_cfg = cfg;
  if (g_crypto_cfg.enabled) init_keyring_from_cfg();

  if (g_crypto_cfg.ttl_seconds <= 0) {
    ORCHRA_LOG().warn("ORCHRA: ttl_seconds=%d invalid, forcing default 120", g_crypto_cfg.ttl_seconds);
    g_crypto_cfg.ttl_seconds = 120;
  }
  if (g_crypto_cfg.enabled && g_crypto_cfg.provider.empty()) {
    g_crypto_cfg.provider = "aes-gcm";
  }

  log_crypto_mode();

  if (!redis_ptr) {
    try {
      redis_ptr = std::make_unique<Redis>(url);
      Logger::smf_app().info("ORCHRA: Redis initialized at %s", url.c_str());
    } catch (const sw::redis::Error& e) {
      Logger::smf_app().error("ORCHRA: Redis init failed: %s", e.what());
      redis_ptr.reset();
    } catch (const std::exception& e) {
      Logger::smf_app().error("ORCHRA: Redis init failed: %s", e.what());
      redis_ptr.reset();
    }
  }
}

bool export_snapshot_to_redis(const OrchraUeContextSnapshot& snap) {

  Logger::smf_app().info(
    "ORCHRA-DBG snapshot export: ctx_supi=%s pdu=%u key=%s redis_ptr=%p",
    snap.supi.c_str(), (unsigned)snap.pdu_session_id,
    ("orchra:ue:" + snap.supi).c_str(), redis_ptr.get());


  if (!redis_ptr) {
    Logger::smf_app().error("ORCHRA: Cannot export; Redis pointer is null.");
    return false;
  }

  nlohmann::json j;
  try {
    j["supi"] = snap.supi;
    j["pdu_session_id"] = (int)snap.pdu_session_id;
    j["dnn"] = snap.dnn;
    j["sst"] = snap.sst;
    j["sd"] = snap.sd;
    j["ip"] = snap.ip;
    j["kseaf"] = snap.kseaf;
    j["kamf"] = snap.kamf;
    j["upf_n4_addr"] = snap.upf_n4_addr;
    j["upf_seid"] = snap.upf_seid;

    std::string key = "orchra:ue:" + snap.supi;

    if (!g_crypto_cfg.enabled || g_crypto_cfg.dual_write_plaintext) {
      redis_ptr->set(key, j.dump());
      redis_ptr->expire(key, g_crypto_cfg.ttl_seconds);
    }

    if (g_crypto_cfg.enabled && g_crypto_cfg.write_encrypted_shadow) {
      if (g_crypto_cfg.provider != "aes-gcm") {
        ORCHRA_LOG().error("ORCHRA: only aes-gcm write supported");
        return false;
      }

      auto it = g_keyring.find(g_active_kid);
      if (it == g_keyring.end()) {
        ORCHRA_LOG().error("ORCHRA: active kid missing");
        return false;
      }
      if (!valid_aes_key_len(it->second)) {
        ORCHRA_LOG().error("ORCHRA: active kid has invalid key length");
        return false;
      }

      std::string plain = j.dump();
      std::vector<uint8_t> pt(plain.begin(), plain.end()), nonce, cttag;
      if (!aes_gcm_encrypt(it->second, pt, g_crypto_cfg.aad, nonce, cttag)) {
        ORCHRA_LOG().error("ORCHRA: aes-gcm encrypt failed");
        return false;
      }

      nlohmann::json env;
      env["_enc"] = "aes-gcm";
      env["_v"] = 2;
      env["_kid"] = g_active_kid;
      env["_ser"] = "json";
      env["_aad"] = g_crypto_cfg.aad;
      env["nonce"] = b64url_encode(nonce);
      env["ciphertext"] = b64url_encode(cttag);

      std::string shadow_key = "enc:" + key;
      redis_ptr->set(shadow_key, env.dump());
      redis_ptr->expire(shadow_key, g_crypto_cfg.ttl_seconds);
    }

    Logger::smf_app().info("ORCHRA: Stored snapshot in Redis for SUPI: %s", snap.supi.c_str());
    return true;

  } catch (const Error& e) {
    Logger::smf_app().error("ORCHRA: Redis export failed: %s", e.what());
  } catch (const std::exception& e) {
    Logger::smf_app().error("ORCHRA: Redis export failed: %s", e.what());
  }

  return false;
}

bool export_snapshot_to_redis_encrypted(const OrchraUeContextSnapshot& snap) {
  auto prev = g_crypto_cfg;
  g_crypto_cfg.enabled = true;
  g_crypto_cfg.dual_write_plaintext = false;
  g_crypto_cfg.write_encrypted_shadow = true;
  if (g_crypto_cfg.provider.empty()) {
    g_crypto_cfg.provider = "aes-gcm";
  }
  if (g_keyring.empty()) init_keyring_from_cfg();
  log_crypto_mode();

  bool ok = export_snapshot_to_redis(snap);
  g_crypto_cfg = prev;
  return ok;
}

static std::optional<OrchraUeContextSnapshot> parse_snapshot(const nlohmann::json& j) {
  try {
    OrchraUeContextSnapshot snap;
    snap.supi = j.value("supi", "");
    snap.pdu_session_id = static_cast<uint8_t>(j.value("pdu_session_id", 0));
    snap.dnn = j.value("dnn", "");
    snap.sst = j.value("sst", static_cast<uint8_t>(0));
    snap.sd = j.value("sd", "");
    snap.ip = j.value("ip", "");
    snap.kseaf = j.value("kseaf", "");
    snap.kamf = j.value("kamf", "");
    snap.upf_n4_addr = j.value("upf_n4_addr", "");
    snap.upf_seid = j.value("upf_seid", 0ull);

    if (snap.supi.empty() || snap.pdu_session_id == 0 || snap.dnn.empty()) {
      ORCHRA_LOG().warn(
          "ORCHRA: snapshot missing required fields (supi='%s', pdu=%u, dnn='%s')",
          snap.supi.c_str(), snap.pdu_session_id, snap.dnn.c_str());
      return std::nullopt;
    }

    return snap;
  } catch (const std::exception& e) {
    ORCHRA_LOG().error("ORCHRA: parse_snapshot failed: %s", e.what());
    return std::nullopt;
  }
}

std::optional<OrchraUeContextSnapshot> import_snapshot_from_redis_compat(const std::string& supi) {

  Logger::smf_app().info(
    "ORCHRA-DBG snapshot import: supi=%s key=%s redis_ptr=%p",
    supi.c_str(), ("orchra:ue:" + supi).c_str(), redis_ptr.get());

  if (!redis_ptr) return std::nullopt;

  try {
    std::string key = "orchra:ue:" + supi;

    if (g_crypto_cfg.enabled) {
      auto enc_val = redis_ptr->get("enc:" + key);
      if (enc_val) {
        nlohmann::json dec;
        if (try_decode_envelope_or_plain(*enc_val, dec)) {
          auto s = parse_snapshot(dec);
          if (s) return s;
        }
      }
    }

    auto val = redis_ptr->get(key);
    if (!val) {
      ORCHRA_LOG().warn("ORCHRA: No Redis data for SUPI: %s", supi.c_str());
      return std::nullopt;
    }

    nlohmann::json dec;
    if (!try_decode_envelope_or_plain(*val, dec)) {
      ORCHRA_LOG().warn("ORCHRA: Failed to decode plain/envelope for SUPI: %s", supi.c_str());
      return std::nullopt;
    }

    return parse_snapshot(dec);

  } catch (const std::exception& e) {
    ORCHRA_LOG().error("ORCHRA: Redis import failed: %s", e.what());
    return std::nullopt;
  }
}

std::optional<OrchraUeContextSnapshot> import_snapshot_from_redis(const std::string& supi) {
  auto s = import_snapshot_from_redis_compat(supi);
  if (!s) {
    Logger::smf_app().warn("ORCHRA: import_snapshot_from_redis returned null for SUPI: %s", supi.c_str());
  }
  return s;
}

}  // namespace orchra
