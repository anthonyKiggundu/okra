#!/usr/bin/env python3
"""
PFCP Adapter (lab-friendly)
- Exposes POST /pfcp/reconfigure that sends a PFCP-style UDP message to the UPF.
- Minimal PFCP header builder + optional TLV payload builder.

It exposes a simple REST API (POST /pfcp/reconfigure) that the orchestrator calls with a JSON payload 
describing the intended PFCP action (e.g., session modification). 
The adapter then sends a PFCP-style UDP message to the target UPF (port 8805 by default) and waits for a response.

Important: the implementation below is a lab-friendly, lightweight sender — it does not implement 
the full RFC-7841 PFCP stack. Instead it builds a minimal PFCP header + user-supplied TLVs (or a small, common PFCP body)
and sends it over UDP. This is appropriate for testing and integration with OAI UPF in a lab. 
For production or full protocol compliance, replace the builder with a complete PFCP library or extend it 
to fully implement sequence numbers, IEs, retransmission logic, and message parsing.
"""

import asyncio
import socket
import struct
import logging
import os
from typing import Optional, Dict, Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pfcp-adapter")

# Configuration via env vars
PFCP_PORT = int(os.getenv("PFCP_PORT", "8805"))
PFCP_BIND_ADDR = os.getenv("PFCP_BIND_ADDR", "0.0.0.0")  # local bind address for socket if needed
DEFAULT_TIMEOUT = float(os.getenv("PFCP_TIMEOUT", "3.0"))  # seconds

app = FastAPI(title="PFCP Adapter (Lab)", version="0.1")


# -----------------------------
# Pydantic models for API input
# -----------------------------
class UpfTarget(BaseModel):
    ip: str
    port: Optional[int] = Field(default=PFCP_PORT)


class PFCPTLV(BaseModel):
    # A simple custom TLV element used by the adapter for payload; arbitrary IE handling.
    ie_type: int
    ie_value: bytes


class PFCPReconfigRequest(BaseModel):
    """
    Example JSON:
    {
      "seid": 12345,
      "message_type": "session_modification",   # optional, mapped internally
      "seq": 10,                                # optional sequence number
      "payload": { ... }                        # optional dict used to build TLVs or raw payload
      "raw_payload_hex": "abcd..."              # optional raw hex payload (preferred when you need precise bytes)
      "upf": { "ip": "10.1.1.5", "port": 8805 }
    }
    """
    seid: int
    message_type: Optional[str] = "session_modification"
    seq: Optional[int] = None
    raw_payload_hex: Optional[str] = None
    # payload: Optional[Dict[str, Any]] = None  # left extensible for custom builders
    upf: UpfTarget


# -----------------------------
# Minimal PFCP header construction
# -----------------------------
# NOTE: This constructs a simplified PFCP header:
#  Octet 0: Version(3) | MP(1) | S(1) | Spare(3)
#  Octet 1: Message Type (uint8)
#  Octet 2-3: Message Length (uint16) - length of message body (not including 4-byte header if S=0)
#  If S=1, then SEID (8 bytes) follows, then Sequence Number (3 bytes) + Spare(1)
#
# For lab tests we set S=1 and include SEID.
#
def build_pfcp_header(message_type: int, seid: int = 0, seq: Optional[int] = None) -> bytes:
    """
    Build a minimal PFCP header with S=1 (includes SEID).
    This is simplified and intended for test usage only.
    """
    version = 1
    S_flag = 1  # include SEID
    MP_flag = 0
    first_octet = (version << 5) | (MP_flag << 4) | (S_flag << 3)

    # message type is a single octet
    msg_type_octet = message_type & 0xFF

    # Body length to fill later (2 bytes) — placeholder zeros for now
    length_placeholder = 0

    header = struct.pack("!BBH", first_octet, msg_type_octet, length_placeholder)

    # SEID (8 bytes) when S=1
    header += struct.pack("!Q", seid & 0xFFFFFFFFFFFFFFFF)

    # Sequence number (3 bytes) + spare (1 byte)
    seq_num = seq if seq is not None else 0
    seq_num = seq_num & 0xFFFFFF
    header += struct.pack("!I", seq_num)[1:]  # take last 3 bytes from 4-byte packing (big-endian)
    header += b'\x00'  # spare

    return header


def finalize_pfcp_message(header: bytes, body: bytes) -> bytes:
    """
    Patch the length field (2 bytes at offset 2) to be len(body).
    Return full message header|body.
    """
    body_len = len(body)
    # replace bytes 2..3 with body_len
    header = bytearray(header)
    header[2] = (body_len >> 8) & 0xFF
    header[3] = body_len & 0xFF
    return bytes(header) + body


# -----------------------------
# Minimal payload builder utilities
# -----------------------------
def hex_to_bytes(hexstr: str) -> bytes:
    hexstr = hexstr.strip()
    if len(hexstr) % 2 != 0:
        hexstr = "0" + hexstr
    return bytes.fromhex(hexstr)


# -----------------------------
# Async UDP send/receive helper
# -----------------------------
async def send_pfcp_and_receive(upf_ip: str, upf_port: int, message: bytes, timeout: float = DEFAULT_TIMEOUT) -> Optional[bytes]:
    """
    Send a UDP PFCP message to upf_ip:upf_port and wait for a single response within timeout.
    Uses asyncio Datagram API to avoid blocking event loop.
    """
    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(lambda: asyncio.DatagramProtocol(), remote_addr=(upf_ip, upf_port))
    try:
        logger.info(f"Sending PFCP message to {upf_ip}:{upf_port} ({len(message)} bytes)")
        transport.sendto(message)
        fut = loop.create_future()

        # Temporary protocol that captures the first packet received
        class CaptureProto(asyncio.DatagramProtocol):
            def datagram_received(self, data, addr):
                if not fut.done():
                    fut.set_result((data, addr))

            def error_received(self, exc):
                if not fut.done():
                    fut.set_exception(exc)

        # create local endpoint to receive
        recv_transport, recv_protocol = await loop.create_datagram_endpoint(lambda: CaptureProto(), local_addr=('0.0.0.0', 0))
        try:
            done, pending = await asyncio.wait([fut], timeout=timeout)
            if not fut.done():
                logger.warning("No PFCP response received (timeout)")
                return None
            data, addr = fut.result()
            logger.info(f"Received PFCP response from {addr}, {len(data)} bytes")
            return data
        finally:
            recv_transport.close()
    finally:
        transport.close()


# -----------------------------
# Message type mapping (lab defaults)
# -----------------------------
# PFCP message type numbers per RFC (lab simplified mapping)
PFCP_MESSAGE_TYPES = {
    "association_setup": 1,
    "association_update": 2,
    "association_release": 3,
    "heartbeat_request": 4,
    "heartbeat_response": 5,
    "session_establishment_request": 50,
    "session_establishment_response": 51,
    "session_modification_request": 52,
    "session_modification_response": 53,
    "session_deletion_request": 54,
    "session_deletion_response": 55
}


# -----------------------------
# API Endpoint
# -----------------------------
@app.post("/pfcp/reconfigure")
async def pfcp_reconfigure(req: PFCPReconfigRequest):
    """
    Accepts JSON describing PFCP action and forwards a PFCP-style message to the UPF.
    Example request body:
    {
      "seid": 12345,
      "message_type": "session_modification_request",
      "seq": 10,
      "raw_payload_hex": "01020304...",
      "upf": { "ip": "10.1.1.5", "port": 8805 }
    }
    """
    # Validate message type
    msg_name = (req.message_type or "session_modification").lower()
    # allow either  'session_modification' or 'session_modification_request'
    if msg_name.endswith("_request") or msg_name.endswith("_response"):
        # leave as-is
        pass
    else:
        # normalize "session_modification" -> "session_modification_request"
        msg_name = msg_name + "_request"

    # find numeric type
    msg_type_num = PFCP_MESSAGE_TYPES.get(msg_name.replace("_request","_request").replace("_response","_response"), None)
    if msg_type_num is None:
        # try without suffix
        base = req.message_type
        msg_type_num = PFCP_MESSAGE_TYPES.get(base, None)
    if msg_type_num is None:
        # fallback to session_modification_request
        msg_type_num = PFCP_MESSAGE_TYPES["session_modification_request"]

    # Build raw body
    if req.raw_payload_hex:
        try:
            body = hex_to_bytes(req.raw_payload_hex)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid raw_payload_hex: {e}")
    else:
        # If no raw payload, build an empty body (or minimal TLV)
        # Here we build a small placeholder IE: IE type 1 (dummy), length 4, value = 0x00000001
        ie_type = 1
        ie_value = b'\x00\x00\x00\x01'
        ie_len = len(ie_value)
        body = struct.pack("!BH", ie_type, ie_len) + ie_value

    # Build header
    header = build_pfcp_header(message_type=msg_type_num, seid=req.seid, seq=req.seq)
    message = finalize_pfcp_message(header, body)

    # Send and optionally wait for response
    upf_ip = req.upf.ip
    upf_port = req.upf.port or PFCP_PORT

    try:
        resp = await send_pfcp_and_receive(upf_ip, upf_port, message, timeout=DEFAULT_TIMEOUT)
    except Exception as e:
        logger.exception("PFCP send/recv failed")
        raise HTTPException(status_code=500, detail=f"PFCP send failed: {e}")

    # If response bytes are received, return hex payload for debugging
    if resp:
        return {"status": "ok", "reply_hex": resp.hex()}
    else:
        return {"status": "sent", "reply_hex": None}


@app.get("/")
async def root():
    return {"service": "pfcp-adapter", "mode": "lab", "pfcp_port": PFCP_PORT}

