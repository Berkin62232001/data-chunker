"""Single-owner API authentication and bounded HTTP request ingestion."""
import secrets
import time
from collections import deque
from tempfile import SpooledTemporaryFile

from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from core.config import settings


class RequestSecurityMiddleware:
    def __init__(self, app):
        self.app = app
        self.requests = deque()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] == "/health":
            return await self.app(scope, receive, send)
        headers = Headers(scope=scope)

        async def reject(status, detail):
            await JSONResponse({"detail": detail}, status_code=status)(scope, receive, send)

        if not settings.api_access_key:
            return await reject(503, "Configure API_ACCESS_KEY before using the API.")
        supplied = headers.get("authorization", "")
        expected = "Bearer " + settings.api_access_key.get_secret_value()
        if not secrets.compare_digest(supplied.encode(), expected.encode()):
            return await reject(401, "A valid access key is required.")

        now = time.monotonic()
        while self.requests and self.requests[0] <= now - 60:
            self.requests.popleft()
        if len(self.requests) >= settings.requests_per_minute:
            return await reject(429, "Request limit reached. Try again in one minute.")
        self.requests.append(now)

        limit = settings.max_request_size_mb * 1024 * 1024
        try:
            declared = int(headers.get("content-length", "0"))
        except ValueError:
            return await reject(400, "Invalid Content-Length.")
        if declared < 0:
            return await reject(400, "Invalid Content-Length.")
        if declared > limit:
            return await reject(413, "Request body exceeds the configured limit.")

        # Bound chunked bodies before multipart parsing, including temporary disk use.
        with SpooledTemporaryFile(max_size=settings.request_spool_bytes) as body:
            size = 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                data = message.get("body", b"")
                size += len(data)
                if size > limit:
                    return await reject(413, "Request body exceeds the configured limit.")
                await run_in_threadpool(body.write, data)
                if not message.get("more_body", False):
                    break
            await run_in_threadpool(body.seek, 0)
            finished = False

            async def bounded_receive():
                nonlocal finished
                if finished:
                    return await receive()
                data = await run_in_threadpool(body.read, settings.request_spool_bytes)
                finished = body.tell() >= size
                return {"type": "http.request", "body": data, "more_body": not finished}

            await self.app(scope, bounded_receive, send)
