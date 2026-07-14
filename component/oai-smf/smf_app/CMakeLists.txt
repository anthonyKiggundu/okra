################################################################################
# Licensed to the OpenAirInterface (OAI) Software Alliance under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The OpenAirInterface Software Alliance licenses this file to You under
# the OAI Public License, Version 1.1  (the "License"); you may not use this file
# except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.openairinterface.org/?page_id=698
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#-------------------------------------------------------------------------------
# For more information about the OpenAirInterface (OAI) Software Alliance:
#      contact@openairinterface.org
################################################################################

include_directories(${SRC_TOP_DIR}/api-server/api)
include_directories(${SRC_TOP_DIR}/api-server/impl)
include_directories(${SRC_TOP_DIR}/api-server/)
include_directories(${SRC_TOP_DIR}/common)
include_directories(${SRC_TOP_DIR}/common/msg)
include_directories(${SRC_TOP_DIR}/common/utils)
include_directories(${SRC_TOP_DIR}/common/bstr)
include_directories(${SRC_TOP_DIR}/common/nas)
include_directories(${SRC_TOP_DIR}/itti)
include_directories(${SRC_TOP_DIR}/pfcp)
include_directories(${SRC_TOP_DIR}/smf)
include_directories(${SRC_TOP_DIR}/udp)
include_directories(${SRC_TOP_DIR}/${MOUNTED_COMMON}/logger)
include_directories(${SRC_TOP_DIR}/${MOUNTED_COMMON}/model/smf)
include_directories(${SRC_TOP_DIR}/${MOUNTED_COMMON}/model/udm)
include_directories(${SRC_TOP_DIR}/${MOUNTED_COMMON}/nas/ies)
include_directories(${SRC_TOP_DIR}/${MOUNTED_COMMON}/nas/common)
include_directories(${SRC_TOP_DIR}/${MOUNTED_COMMON}/nas/utils)
include_directories(${SRC_TOP_DIR}/${MOUNTED_COMMON}/nas/5gsm-msgs)
include_directories(${SRC_TOP_DIR}/${MOUNTED_COMMON}/ngap/libngap)
include_directories(${SRC_TOP_DIR}/${MOUNTED_COMMON}/ngap/libngap_ies)
include_directories(${SRC_TOP_DIR}/${MOUNTED_COMMON}/ngap/ngap_ies)
include_directories(${SRC_TOP_DIR}/${MOUNTED_COMMON}/utils)
include_directories(${CMAKE_CURRENT_SOURCE_DIR})
include(${SRC_TOP_DIR}/${MOUNTED_COMMON}/config/config.cmake)
include(${SRC_TOP_DIR}/${MOUNTED_COMMON}/utils/utils.cmake)
include(${SRC_TOP_DIR}/${MOUNTED_COMMON}/common/common.cmake)
include(${SRC_TOP_DIR}/${MOUNTED_COMMON}/http/http.cmake)

include(${BUILD_TOP_DIR}/smf/used_models.cmake)
add_definitions(-D_GLIBCXX_USE_CXX11_ABI=1)

add_definitions(-DCOMPILING_FOR_SMF)

add_library (SMF_APP SHARED  
  smf_app.cpp
  smf_config.cpp
  smf_context.cpp
  smf_n1.cpp
  smf_n2.cpp
  smf_pfcp_association.cpp
  smf_pco.cpp
  smf_procedure.cpp
  smf_n4.cpp
  smf_n7.cpp
  smf_sbi.cpp
  smf_event.cpp
  smf_profile.cpp
  smf_subscription.cpp
  smf_msg.cpp
  smf_config_types.cpp
  smf_qos_upf_edge.cpp
  session_handler.cpp
  orchra_context.cpp
  orchra_pfcp.cpp
  orchra_redis.cpp
  options.cpp

)

find_package(OpenSSL REQUIRED)

target_include_directories(SMF_APP PUBLIC #PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_SOURCE_DIR}/src/oai-cn5g-common-src/pfcp
    /usr/local/include
)

# 2. Add the link instructions at the bottom
target_link_libraries(SMF_APP
    PRIVATE
    redis++
    hiredis
    pthread
    OpenSSL::Crypto
    zstd
)
