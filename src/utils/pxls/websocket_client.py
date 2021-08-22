import asyncio
import json
import threading
import websockets

class WebsocketClient:
    """A threaded websocket client to update the canvas board and online count
     in real-time."""

    def __init__(self, uri: str, stats_manager):
        self.uri = uri
        self.stats = stats_manager
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._start, daemon=True)
        self._paused = False

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
            try:
                async with websockets.connect(self.uri) as websocket:
                    print("Websocket connected")
                    async for message in websocket:
                        while self._paused:
                            pass
                        try:
                            message_json = json.loads(message)

                            if message_json["type"] == "pixel":
                                pixels = message_json["pixels"]
                                for pixel in pixels:
                                    self.stats.update_board_pixel(**pixel)
                                    self.stats.update_virginmap_pixel(**pixel)
                            if message_json["type"] == "users":
                                count = message_json["count"]
                                self.stats.online_count = count

                        except Exception as error:
                            print(f"Websocket client raised {error}")
            except Exception as error:
                print(f"Websocket disconnected: {error}")
                print("Attempting reconnect...")
                await asyncio.sleep(1)
