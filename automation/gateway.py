"""The unary gRPC-Web contract shipped in IMServerless UI 2.7.0."""

from contextlib import contextmanager
import os
import socket
import struct
import subprocess
import tempfile
import time
import urllib.request

def varint(number):
    result = bytearray()
    while number > 127:
        result.append((number & 127) | 128)
        number >>= 7
    result.append(number)
    return bytes(result)


def strings(fields):
    result = bytearray()
    for number, value in fields.items():
        if not 1 <= number <= 15 or not isinstance(value, str):
            raise ValueError("Expected known string request fields")
        if value:
            value = value.encode("utf-8")
            result.extend(varint(number * 8 + 2) + varint(len(value)) + value)
    return bytes(result)


def protobuf(data):
    """Decode only the string/message and bool fields used by these replies."""
    offset = 0
    fields = {}

    def integer():
        nonlocal offset
        value = 0
        for shift in range(0, 70, 7):
            if offset >= len(data):
                raise ValueError("Truncated protobuf integer")
            byte = data[offset]
            offset += 1
            value |= (byte & 127) << shift
            if not byte & 128:
                return value
        raise ValueError("Oversized protobuf integer")

    while offset < len(data):
        tag = integer()
        number, wire = tag >> 3, tag & 7
        if not number:
            raise ValueError("Invalid protobuf field")
        if wire == 0:
            value = integer()
        elif wire == 2:
            size = integer()
            if size > len(data) - offset:
                raise ValueError("Truncated protobuf field")
            value = data[offset:offset + size]
            offset += size
        else:
            raise ValueError(f"Unsupported response wire type {wire}; recheck the UI contract")
        fields.setdefault(number, []).append(value)
    return fields


def text(fields, number):
    return fields.get(number, [b""])[0].decode("utf-8")


def succeeded(fields, success=1, error=2):
    if fields.get(success, [0])[0] != 1:
        raise RuntimeError(text(fields, error) or "IMServerless rejected the request")


def decode_reply(body):
    messages = []
    trailers = {}
    offset = 0
    while offset < len(body):
        if len(body) - offset < 5:
            raise ValueError("Truncated gRPC-Web frame")
        flags, size = struct.unpack_from(">BI", body, offset)
        offset += 5
        if size > len(body) - offset:
            raise ValueError("Truncated gRPC-Web payload")
        payload = body[offset:offset + size]
        offset += size
        if flags == 128:
            trailers.update(line.split(":", 1) for line in payload.decode("ascii").split("\r\n") if line)
        elif flags == 0:
            messages.append(payload)
        else:
            raise ValueError("Unsupported gRPC-Web framing")
    if trailers.get("grpc-status", "").strip() != "0":
        raise RuntimeError("gRPC-Web failed: " + str(trailers))
    if len(messages) != 1:
        raise ValueError("Expected one unary IMServerless reply")
    return protobuf(messages[0])


class Gateway:
    def __init__(self, port):
        self.base = f"http://127.0.0.1:{port}/deploymentgateway.DeploymentGatewaySvc/"
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def call(self, method, fields):
        if method not in {"CreateApp", "Modify", "QueryAppVersion", "QueryAppStatus"}:
            raise ValueError("Unsupported deployment operation")
        payload = strings(fields)
        request = urllib.request.Request(self.base + method,
            data=b"\0" + struct.pack(">I", len(payload)) + payload,
            headers={"Content-Type": "application/grpc-web+proto", "X-Grpc-Web": "1"})
        # No mutation retries: a lost response may still mean the operation succeeded.
        with self.opener.open(request, timeout=90) as response:
            body = response.read(10_000_001)
        if len(body) > 10_000_000:
            raise ValueError("IMServerless response exceeds the supported size")
        return decode_reply(body)


@contextmanager
def tunnel(kubeconfig, context):
    # Kubernetes authenticates and encrypts the connection to the internal gateway.
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    environment = os.environ.copy()
    bypass = environment.get("NO_PROXY", "") + ",imcloud-rancher-k8s.s33prod.mfg.intel.com"
    environment.update(NO_PROXY=bypass, no_proxy=bypass)
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as log:
        process = subprocess.Popen([
            "kubectl", "--kubeconfig", str(kubeconfig), "--context", context,
            "-n", "imserverless", "port-forward", "--address", "127.0.0.1",
            "service/deployment-gateway", f"{port}:50053",
        ], stdout=log, stderr=log, env=environment)
        try:
            for _ in range(60):
                if process.poll() is not None:
                    raise RuntimeError("Gateway tunnel failed; check context, network and port-forward permissions")
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.25)
            else:
                raise TimeoutError("Gateway tunnel did not become ready")
            yield Gateway(port)
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
