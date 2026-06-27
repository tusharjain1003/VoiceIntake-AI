import asyncio
import logging
from typing import Optional

from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType
from deepgram.listen.v1.types.listen_v1results import ListenV1Results

logger = logging.getLogger(__name__)


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
        self.available: bool = False
        self.error: Optional[str] = None

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._done = asyncio.Event()

        client = AsyncDeepgramClient(api_key=self._api_key)

        try:
            async with client.listen.v1.connect(
                model=self._model,
                language=self._language,
                channels=1,
                interim_results=True,
                endpointing=500,
            ) as socket:
                self._socket = socket
                self.available = True
                logger.info(
                    "Deepgram connected (model=%s, lang=%s)",
                    self._model,
                    self._language,
                )

                socket.on(EventType.MESSAGE, self._on_message)
                socket.on(EventType.ERROR, self._on_error)
                socket.on(EventType.CLOSE, self._on_close)

                self._listen_task = asyncio.create_task(socket.start_listening())

                await self._done.wait()

        except Exception as exc:
            self.error = str(exc)
            self.available = False
            logger.error("Deepgram start failed: %s", exc)
        finally:
            self.available = False

    def _on_message(self, data) -> None:
        if not self._loop:
            return
        if isinstance(data, ListenV1Results):
            transcript = data.channel.alternatives[0].transcript
            is_final = data.is_final or False
            if transcript.strip():
                asyncio.run_coroutine_threadsafe(
                    self._queue.put(("transcript", transcript, is_final)),
                    self._loop,
                )

    def _on_error(self, error) -> None:
        logger.error("Deepgram stream error: %s", error)
        if self._loop:
            asyncio.run_coroutine_threadsafe(
                self._queue.put(("error", str(error))),
                self._loop,
            )

    def _on_close(self, _data=None) -> None:
        logger.info("Deepgram connection closed")
        self.available = False
        if self._loop:
            asyncio.run_coroutine_threadsafe(
                self._queue.put(("close",)),
                self._loop,
            )

    async def send(self, data: bytes) -> None:
        if not self.available or not self._socket:
            return
        try:
            await self._socket.send_media(data)
        except Exception as exc:
            logger.warning("Deepgram send error: %s", exc)

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
