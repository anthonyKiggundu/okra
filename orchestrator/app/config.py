import os

K8S_NAMESPACE_BASE = os.getenv("K8S_NAMESPACE_BASE", "oai-core-vanilla")
K8S_NAMESPACE_ORCHRA = os.getenv("K8S_NAMESPACE_ORCHRA", "base-chart")
K8S_NAMESPACE_RIC = "5g-ric"

REDIS_HOST_ORCHRA = os.getenv(
    "REDIS_HOST_ORCHRA",
    f"redis-master.{K8S_NAMESPACE_ORCHRA}.svc.cluster.local"
)

AMF_HOST = f"oai-amf.{K8S_NAMESPACE_BASE}.svc.cluster.local"
SMF_HOST = f"oai-smf.{K8S_NAMESPACE_BASE}.svc.cluster.local"
UPF_HOST = f"oai-upf.{K8S_NAMESPACE_BASE}.svc.cluster.local"
MYSQL_HOST = f"oai-mysql.{K8S_NAMESPACE_BASE}.svc.cluster.local"
AUSF_HOST = f"oai-ausf.{K8S_NAMESPACE_BASE}.svc.cluster.local"
UDM_HOST = f"oai-udm.{K8S_NAMESPACE_BASE}.svc.cluster.local"
UDR_HOST = f"oai-udr.{K8S_NAMESPACE_BASE}.svc.cluster.local"

AMF_HOST_ORCHRA = f"oai-amf.{K8S_NAMESPACE_ORCHRA}.svc.cluster.local"
SMF_HOST_ORCHRA = f"oai-smf.{K8S_NAMESPACE_ORCHRA}.svc.cluster.local"
UPF_HOST_ORCHRA = f"oai-upf.{K8S_NAMESPACE_ORCHRA}.svc.cluster.local"
MYSQL_HOST_ORCHRA = f"oai-mysql.{K8S_NAMESPACE_ORCHRA}.svc.cluster.local"
AUSF_HOST_ORCHRA = f"oai-ausf.{K8S_NAMESPACE_ORCHRA}.svc.cluster.local"
UDM_HOST_ORCHRA = f"oai-udm.{K8S_NAMESPACE_ORCHRA}.svc.cluster.local"
UDR_HOST_ORCHRA = f"oai-udr.{K8S_NAMESPACE_ORCHRA}.svc.cluster.local"

MOSAIC_CONTROLLER_URL = "http://10.42.0.144:8000/v1/slice-switch"
#os.getenv(
#    "MOSAIC_CONTROLLER_URL",
#    f"http://slice-controller-baseline.{K8S_NAMESPACE_BASE}.svc.cluster.local:8000/trigger-mosaic-migration"
#)

#MOSAIC_CONTROLLER_URL = f"http://slice-controller-baseline.{K8S_NAMESPACE_BASE}.svc.cluster.local:8000/trigger-mosaic-migration"
#MOSAIC_CONTROLLER_URL = os.getenv("MOSAIC_CONTROLLER_URL", "http://127.0.0.1:8000/trigger-mosaic-migration")

# We should not have redis_url for the base but instead redis_url for orchra
# but we use the redis in the base-chart namespace for now for testing stuff

# REDIS_URL = f"redis://{REDIS_HOST_ORCHRA}:6379/0"
# REDIS_URL = f"redis://{REDIS_HOST_BASE}:6379/0"
# We do a port forwarding due to DNS issues 
# On cmd: => kubectl port-forward -n base-chart svc/redis-master 6379:6379
# Then set:
REDIS_URL = "redis://127.0.0.1:6380/0" ## 6380 because 6379 is already in use for now


