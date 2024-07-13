import asyncio
import json
import threading
import uuid

import websockets

from utils.log import get_logger

logger = get_logger("pxls_websocket")


class WebsocketClient:
    """A threaded websocket client to update the canvas board and online count
    in real-time."""

    def __init__(self, uri: str, stats_manager, cfauth):
        self.uri = uri
        self.stats = stats_manager
        self.pxls_cfauth = cfauth
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._start, daemon=True)
        self._paused = False
        self.status = False

    def start(self):
        """Start the websocket in a separate thread."""
        self.thread.start()

    def _start(self):
        self.loop.run_until_complete(self._listen())

    def pause(self):
        """Pause the websocket."""
        self._paused = True

    def resume(self):
        """Resume the websocket."""
        self._paused = False

    async def _listen(self):

        while True:
            pxls_validate = str(uuid.uuid4())
            if self.pxls_cfauth:
                headers = {
                    "Cookie": f"pxls-validate={pxls_validate}",
                    "x-pxls-cfauth": f"{self.pxls_cfauth}"
                }
            else:
                headers = {
                    "Cookie": f"pxls-validate={pxls_validate}"
                }
            try:
                async with websockets.connect(
                    self.uri, extra_headers=headers
                ) as websocket:
                    self.status = True
                    logger.info("Websocket connected")
                    async for message in websocket:
                        while self._paused:
                            pass
                        try:
                            message_json = json.loads(message)

                            if message_json["type"] == "pixel":
                                pixels = message_json["pixels"]
                                for pixel in pixels:
                                    if self.stats.board_array is not None:
                                        self.stats.update_board_pixel(**pixel)
                                    if self.stats.virginmap_array is not None:
                                        self.stats.update_virginmap_pixel(**pixel)
                            if message_json["type"] == "users":
                                count = message_json["count"]
                                self.stats.online_count = count

                        except Exception:
                            logger.exception("Websocket client raised")
            except Exception as error:
                self.status = False
                self.stats.online_count = None
                logger.debug(f"Websocket disconnected: {error}")
                logger.debug("Attempting reconnect...")
                await asyncio.sleep(1)
