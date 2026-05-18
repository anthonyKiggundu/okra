import aiohttp
import async_timeout
from typing import Dict, Any, Optional

HTTP_TIMEOUT = 5  

class SliceClient:
    def __init__(self, base_url: str, session: aiohttp.ClientSession):
        self.base_url = base_url.rstrip("/")
        self.session = session

    async def get_ue_context(self, ue_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/ue-context/{ue_id}"
        async with async_timeout.timeout(HTTP_TIMEOUT):
            async with self.session.get(url) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def post_ue_context(self, ue_id: str, context: Dict[str, Any]) -> None:
        url = f"{self.base_url}/ue-context/{ue_id}"
        async with async_timeout.timeout(HTTP_TIMEOUT):
            async with self.session.post(url, json=context) as resp:
                resp.raise_for_status()

    async def nsmf_pdusession_create(self, ue_id: str, source_context: Dict):
        url = f"{self.base_url}/nsmf-pdusession/v1/sm-contexts"
        payload = {
            "ue_id": ue_id,
            "s_nssai": {"sst": 1, "sd": "000001"},
            "source_smf_uri": source_context.get("smf_uri", "http://localhost:8001"),
            "pdu_session_id": source_context.get("pdu_id", 1)
        }
        async with self.session.post(url, json=payload) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def namf_comm_release(self, ue_id: str):
        url = f"{self.base_url}/namf-comm/v1/ue-contexts/{ue_id}/release"
        async with self.session.post(url, json={"cause": "SLICE_MIGRATION_COMPLETE"}) as resp:
            return resp.status == 204

    async def namf_comm_get_context(self, ue_id: str) -> Dict:
        async with self.session.get(f"{self.base_url}/namf-comm/v1/ue-contexts/{ue_id}") as resp:
            resp.raise_for_status()
            return await resp.json()

    async def nsmf_pdusession_import_notification(self, ue_id: str):
        url = f"{self.base_url}/nsmf-pdusession/v1/import-context"
        async with self.session.post(url, json={"ue_id": ue_id, "source": "redis"}) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def confirm_binding(self, ue_id: str):
        async with self.session.get(f"{self.base_url}/confirm/{ue_id}") as resp:
            return resp.status == 200
        
    async def commit_session(self, ue_id: str, pdu_id: int):
        url = f"{self.base_url}/nsmf-pdusession/v1/commit"
        async with self.session.post(url, json={"ue_id": ue_id, "pdu_id": pdu_id}) as resp:
            resp.raise_for_status()


class FlexRANClient:
    def __init__(self, base_url: str, session: aiohttp.ClientSession):
        self.session = session
        self.base_url = base_url.rstrip("/")

    async def notify_slice_change(self, ue_id: str, new_slice: str) -> None:
        url = f"{self.base_url}/slice-change"
        payload = {"ue_id": ue_id, "new_slice": new_slice}
        async with async_timeout.timeout(HTTP_TIMEOUT):
            async with self.session.post(url, json=payload) as resp:
                resp.raise_for_status()


class UPFClient:
    def __init__(self, base_url: str, session: aiohttp.ClientSession):
        self.session = session
        self.base_url = base_url.rstrip("/")

    async def reconfigure_tunnels(self, ue_id: str, pdu_id: int, params: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/pfcp/reconfigure"
        async with async_timeout.timeout(HTTP_TIMEOUT):
            async with self.session.post(url, json={"ue_id": ue_id, "pdu_id": pdu_id, **params}) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def create_shadow_tunnel(self, ue_id: str, pdu_id: int, target_params: Dict):
        url = f"{self.base_url}/n4/sessions/{ue_id}/modify"
        payload = {
            "node_id": "upf-core-01",
            "pdu_session_id": pdu_id,
            "operations": [
                {
                    "type": "CREATE_PDR",
                    "pdr_id": 2,
                    "precedence": 10,
                    "pdi": {
                        "source_interface": "ACCESS",
                        "local_teid": target_params.get("target_teid", 101),
                        "ue_ip_address": target_params.get("ue_ip", "10.0.0.1")
                    },
                    "far_id": 2
                }
            ]
        }
        async with self.session.post(url, json=payload) as resp:
            if resp.status != 200:
                raise Exception("UPF Shadow Tunnel Allocation Failed")
            return await resp.json()
