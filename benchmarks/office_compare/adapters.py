from __future__ import annotations

from dataclasses import dataclass
import json
import mimetypes
from pathlib import Path
import socket
import time
from typing import Any
from urllib import error, request
from uuid import uuid4


@dataclass
class ChatResult:
    answer: str
    artifacts: list[dict[str, Any]]
    elapsed_seconds: float
    raw: dict[str, Any]


def _json_request(method: str, url: str, payload: dict[str, Any] | None = None, timeout: int = 180) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    for attempt in range(3):
        try:
            with request.urlopen(req, timeout=timeout) as response:
                body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if exc.code < 500 or attempt == 2:
                raise RuntimeError(f"{method} {url} returned HTTP {exc.code}: {body}") from exc
        except (error.URLError, TimeoutError, socket.timeout) as exc:
            if attempt == 2:
                reason = getattr(exc, "reason", str(exc))
                raise RuntimeError(f"{method} {url} failed: {reason}") from exc
        time.sleep(2)
    raise RuntimeError(f"{method} {url} failed after retries")


def _multipart_upload(url: str, path: Path, timeout: int = 180) -> dict[str, Any]:
    boundary = f"----LongChainBenchmark{uuid4().hex}"
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    body = bytearray()
    body.extend(f"--{boundary}\r\n".encode("ascii"))
    body.extend(f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'.encode("utf-8"))
    body.extend(f"Content-Type: {content_type}\r\n\r\n".encode("ascii"))
    body.extend(path.read_bytes())
    body.extend(f"\r\n--{boundary}--\r\n".encode("ascii"))
    req = request.Request(
        url,
        data=bytes(body),
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"POST {url} returned HTTP {exc.code}: {body_text}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"POST {url} failed: {exc.reason}") from exc


class LongChainAdapter:
    name = "longchain"

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.session_id = ""
        self.uploaded: dict[Path, int] = {}

    def upload(self, path: Path) -> int:
        if path not in self.uploaded:
            self.uploaded[path] = int(_multipart_upload(f"{self.base_url}/api/files/upload", path)["id"])
        return self.uploaded[path]

    def chat(self, prompt: str, file_ids: list[int]) -> ChatResult:
        started = time.perf_counter()
        raw = _json_request(
            "POST",
            f"{self.base_url}/api/chat",
            {"message": prompt, "session_id": self.session_id, "file_ids": file_ids},
        )
        return ChatResult(
            answer=str(raw.get("answer", "")),
            artifacts=list(raw.get("artifacts", [])),
            elapsed_seconds=time.perf_counter() - started,
            raw=raw,
        )

    def reset_session(self, task_id: str) -> None:
        self.session_id = f"bench-longchain-{task_id}-{uuid4().hex}"


class BaselineAdapter:
    name = "conversational-rag-chatbot"

    def __init__(self, base_url: str, model: str = "qwen-plus"):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.session_id = ""
        self.uploaded: dict[Path, int] = {}

    def upload(self, path: Path) -> int:
        if path not in self.uploaded:
            self.uploaded[path] = int(_multipart_upload(f"{self.base_url}/upload-doc", path)["file_id"])
        return self.uploaded[path]

    def chat(self, prompt: str, file_ids: list[int]) -> ChatResult:
        started = time.perf_counter()
        raw = _json_request(
            "POST",
            f"{self.base_url}/chat",
            {"question": prompt, "session_id": self.session_id, "model": self.model},
        )
        return ChatResult(
            answer=str(raw.get("answer", "")),
            artifacts=[],
            elapsed_seconds=time.perf_counter() - started,
            raw=raw,
        )

    def reset_session(self, task_id: str) -> None:
        self.session_id = f"bench-baseline-{task_id}-{uuid4().hex}"
