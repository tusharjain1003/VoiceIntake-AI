import asyncio
import logging
from typing import Any, Optional

from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType
from deepgram.listen.v1.types.listen_v1results import ListenV1Results

logger = logging.getLogger(__name__)

_MAX_PENDING_BYTES = 1_048_576  # 1 MB


class DeepgramStreamClient:
    def __init__(
        self,
        api_key: str,
        model: str = "nova-2",
        language: str = "en",
    ):
        self._api_key = api_key
        self._model = model
        self._language = language
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._socket = None
        self._listen_task: Optional[asyncio.Task] = None
        self._done: Optional[asyncio.Event] = None
        self._queue: asyncio.Queue[tuple] = asyncio.Queue()
        self._connected_event = asyncio.Event()
        self._pending_chunks: list[bytes] = []
        self._pending_bytes: int = 0

        self.available: bool = False
        self.connected: bool = False
        self.closed: bool = False
        self.error: Optional[str] = None
        self.close_code: Optional[int] = None
        self.close_reason: str = ""

        self.chunks_queued: int = 0
        self.bytes_queued: int = 0
        self.chunks_flushed: int = 0
        self.bytes_flushed: int = 0
        self.chunks_forwarded: int = 0
        self.bytes_forwarded: int = 0

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()

        client = AsyncDeepgramClient(api_key=self._api_key)

        try:
            async with client.listen.v1.connect(
                model=self._model,
                language=self._language,
                channels=1,
                interim_results=True,
                endpointing=500,
                smart_format=True,
                punctuate=True,
            ) as socket:
                self._socket = socket
                self.available = True
                self.connected = True
                self._connected_event.set()
                logger.info(
                    "Deepgram connected (model=%s, lang=%s)",
                    self._model,
                    self._language,
                )

                socket.on(EventType.MESSAGE, self._on_message)
                socket.on(EventType.ERROR, self._on_error)
                socket.on(EventType.CLOSE, self._on_close)

                self._done = asyncio.Event()
                self._listen_task = asyncio.create_task(socket.start_listening())

                flush_count = len(self._pending_chunks)
                flush_bytes = self._pending_bytes
                if flush_count > 0:
                    for chunk in self._pending_chunks:
                        await self._socket.send_media(chunk)
                    self.chunks_flushed = flush_count
                    self.bytes_flushed = flush_bytes
                    self._pending_chunks.clear()
                    self._pending_bytes = 0
                    logger.info(
                        "Deepgram flushed %d queued chunks (%d bytes)",
                        flush_count,
                        flush_bytes,
                    )

                self._queue.put_nowait(("connected", flush_count, flush_bytes))

                await self._done.wait()

        except Exception as exc:
            self.error = str(exc)
            self.available = False
            self.connected = False
            logger.error("Deepgram start failed: %s", exc)
        finally:
            self.available = False

    def _on_message(self, data: Any) -> None:
        if not self._loop:
            return
        if isinstance(data, ListenV1Results):
            transcript = data.channel.alternatives[0].transcript
            is_final = data.is_final or False
            speech_final = getattr(data, "speech_final", None)
            logger.info(
                "Deepgram event type=transcript is_final=%s speech_final=%s text=%r",
                is_final,
                speech_final,
                transcript[:200] if transcript else "",
            )
            if transcript.strip():
                asyncio.run_coroutine_threadsafe(
                    self._queue.put(("transcript", transcript, is_final)),
                    self._loop,
                )

    def _on_error(self, error: Any) -> None:
        logger.error("Deepgram stream error: %s", error)
        if self._loop:
            asyncio.run_coroutine_threadsafe(
                self._queue.put(("error", str(error))),
                self._loop,
            )

    def _on_close(self, data: Any = None) -> None:
        code = getattr(data, "code", None) if data is not None else None
        reason = getattr(data, "reason", "") if data is not None else ""
        logger.info("Deepgram connection closed code=%s reason=%s", code, reason)
        self.available = False
        self.connected = False
        self.closed = True
        self.close_code = code
        self.close_reason = reason
        if self._loop:
            asyncio.run_coroutine_threadsafe(
                self._queue.put(("close", code, reason)),
                self._loop,
            )

    async def send(self, data: bytes) -> bool:
        """Forward or queue audio data.

        Returns True if forwarded directly to the socket,
        False if queued for later delivery (or dropped).
        """
        if self.closed:
            return False

        if self.connected and self.available and self._socket:
            try:
                await self._socket.send_media(data)
                self.chunks_forwarded += 1
                self.bytes_forwarded += len(data)
                return True
            except Exception as exc:
                logger.warning("Deepgram send error: %s", exc)
                return False

        self._pending_chunks.append(data)
        self._pending_bytes += len(data)
        self.chunks_queued += 1
        self.bytes_queued += len(data)

        if self._pending_bytes > _MAX_PENDING_BYTES:
            dropped = self._pending_chunks.pop(0)
            self._pending_bytes -= len(dropped)
            logger.warning(
                "Deepgram pending buffer overflow — dropped oldest chunk (%d bytes)",
                len(dropped),
            )

        return False

    async def send_keepalive(self) -> None:
        if not self.connected or not self.available or not self._socket:
            return
        try:
            await self._socket.send_keep_alive()
        except Exception as exc:
            logger.debug("Deepgram keepalive send error: %s", exc)

    async def finalize(self) -> None:
        if not self.connected or not self.available or not self._socket:
            return
        try:
            await self._socket.send_finalize()
        except Exception as exc:
            logger.warning("Deepgram finalize error: %s", exc)

    async def wait_until_connected(self, timeout: float = 10.0) -> bool:
        try:
            await asyncio.wait_for(self._connected_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            return False
        return True

    async def read_event(self) -> tuple:
        return await self._queue.get()

    async def close(self) -> None:
        if self._done:
            self._done.set()
        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
        if self._socket:
            try:
                await self._socket.send_close_stream()
            except Exception:
                pass
        self.available = False
        self.connected = False
        self.closed = True
