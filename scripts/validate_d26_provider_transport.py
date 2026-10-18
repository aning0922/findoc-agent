"""Real production SDK against an isolated loopback connection-cut server.

No credentials/environment files/vendors are accessed. This validates transport
attempt count, not vendor availability or model semantics.
"""

import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import threading
import sys
from openai import Client, APIConnectionError
import httpx
from app.rag.openai_compatible_llm import OpenAICompatibleLLMClient, ProviderCallError

calls = []


class CutConnection(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        calls.append(dict(path=self.path, body_sha256=hashlib.sha256(body).hexdigest()))
        self.connection.shutdown(socket.SHUT_RDWR)
        self.connection.close()

    def log_message(self, *args):
        pass


server = ThreadingHTTPServer(("127.0.0.1", 0), CutConnection)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
port = server.server_port
allowed = (("127.0.0.1", port),)
attempts = []


def guard(event, args):
    if event == "socket.connect":
        attempts.append(args[1])
        if args[1] not in allowed:
            raise RuntimeError("D26 provider test rejects all other service addresses")


sys.addaudithook(guard)
client = Client(
    api_key="isolated-fixture-no-real-credentials",
    base_url=f"http://127.0.0.1:{port}/v1",
    timeout=3,
    http_client=httpx.Client(trust_env=False),
)
llm = OpenAICompatibleLLMClient("d26-isolated-transport", client)
try:
    try:
        llm.generate_once("D26 bounded fixed transport probe")
    except APIConnectionError:
        pass
    else:
        raise AssertionError("connection failure expected")
    assert len(calls) == 1, (len(calls), attempts)
    try:
        llm.complete([dict(role="user", content="D26 bounded transport probe")], [])
    except ProviderCallError as exc:
        assert isinstance(exc.__cause__, APIConnectionError)
    else:
        raise AssertionError("unknown provider failure expected")
    assert len(calls) == 2
    Path(os.environ.get("D26_PROVIDER_EVIDENCE", "product/d26/evidence/b-provider-transport.json")).write_text(
        json.dumps(
            dict(
                port=port,
                allowed_addresses=allowed,
                connection_cut_after_request_body=True,
                generate_once_requests=1,
                complete_requests=1,
                calls=calls,
                automatic_retries=0,
                actual_sdk=True,
                actual_loopback_network=True,
                actual_vendor=False,
                actual_model=False,
                human_acceptances=0,
                other_service_addresses_blocked=True,
            ),
            indent=2,
        )
        + "\n"
    )
finally:
    client.close()
    server.shutdown()
    server.server_close()
    thread.join()
