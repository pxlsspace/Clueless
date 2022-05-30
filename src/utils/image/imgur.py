import json
import os
from io import BytesIO

import aiohttp
from dotenv import find_dotenv, load_dotenv, set_key
from PIL import Image

from utils.log import get_logger
from utils.utils import BadResponseError, in_executor

logger = get_logger(__name__)
API_URL = "https://api.imgur.com/3/"
IMGUR_SIZE_LIMIT = 5 * 2**20  # 5 MB


class Imgur:
    def __init__(self, client_id, client_secret, refresh_token, access_token):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.access_token = access_token

    async def refresh_access_token(self):
        """Refesh the access token and save it in the .env"""
        data = {
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token",
        }

        url = "https://api.imgur.com/oauth2/token"
        response_json = await self.make_request("POST", url, data)
        self.access_token = response_json["access_token"]
        # update the dotenv variable too so it's used at the next restart
        dotenv_file = find_dotenv()
        load_dotenv(dotenv_file)
        os.environ["IMGUR_ACCESS_TOKEN"] = self.access_token
        set_key(dotenv_file, "IMGUR_ACCESS_TOKEN", self.access_token)
        logger.info("Access token updated")

    async def make_request(
        self, method, url, data=None, force_anon=False, check_token=True
    ):
        """Make a request to the imgur API and check for errors. (+ refresh the token if
        the URL returns an error 403)"""
        if force_anon:
            headers = {"Authorization": f"Client-ID {self.client_id}"}
        else:
            headers = headers = {"Authorization": f"Bearer {self.access_token}"}
        async with aiohttp.request(method.lower(), url, headers=headers, data=data) as r:

            if r.status == 403 and check_token:
                # refresh the access token
                await self.refresh_access_token()
                # try again
                return await self.make_request(
                    method, url, data, force_anon, check_token=False
                )

            if r.status != 200:
                raise BadResponseError(f"The URL leads to an error {r.status}")
            response_json = json.loads(await r.text())
        if (
            "status" in response_json and response_json["status"] != 200
        ) or "error" in response_json:
            status = response_json["status"]
            error = response_json["error"]
            print(f"Imgur upload failed: error {status} ({error})")
            raise BadResponseError(f"Imgur upload failed: error {status} ({error})")
        return response_json

    async def get_image(self, image_hash):
        """Get an imgur image using the hash"""
        response_data = await self.make_request("GET", API_URL + f"image/{image_hash}")
        return response_data["data"]

    async def upload_image(self, image, force_anon=False):
        """Upload the input image to imgur, return the image URL.

        - Raises `BadResponseError` if the image is not found
        - Raises `ValueError` if the image is bigger than 5MB"""
        if isinstance(image, Image.Image):
            payload_image = await self.image_to_bytes(image)
            if len(payload_image) > IMGUR_SIZE_LIMIT:
                raise ValueError("This image is too big to be uploaded on imgur.")
        else:
            payload_image = image
        payload = {
            "image": payload_image,
        }
        response_json = await self.make_request(
            "POST", API_URL + "image", payload, force_anon
        )
        return response_json["data"]["link"]

    @in_executor()
    def image_to_bytes(self, image: Image.Image, format="PNG"):
        """converts PIL.Image -> bytes"""
        buffer = BytesIO()
        image.save(buffer, format=format)
        return buffer.getvalue()
