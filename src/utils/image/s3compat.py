import json
import os
from io import BytesIO
import hashlib

from botocore.exceptions import ClientError
import boto3
from dotenv import find_dotenv, load_dotenv, set_key
from PIL import Image

from utils.log import get_logger
from utils.utils import BadResponseError, in_executor

logger = get_logger(__name__)
SIZE_LIMIT = 5 * 2**20  # 5 MB


class S3Compat:
    def __init__(self, access_key, secret_key, endpoint_url, bucket_name, access_url = None):
        self.access_key = access_key
        self.secret_key = secret_key
        self.endpoint_url = endpoint_url
        self.bucket_name = bucket_name
        self.access_url = access_url

    async def upload_image(self, image, custom_metadata=None):
        """Upload the input image to S3-compatible storage, return the image URL."""
        if isinstance(image, Image.Image):
            payload_image = await self.image_to_bytes(image)
            if len(payload_image) > SIZE_LIMIT:
                raise ValueError("This image is too big to be uploaded.")
        else:
            payload_image = image

        # Generate hash from image content
        image_hash = hashlib.sha256(payload_image).hexdigest()[:16]  # Adjust the length as needed

        # Create S3 client
        s3_client = boto3.client(
            's3',
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            endpoint_url=self.endpoint_url
        )

        # Upload image
        filename = f'{image_hash}.png'
        try:
            metadata = custom_metadata if custom_metadata else {}
            response = s3_client.put_object(
                Bucket=self.bucket_name,
                Key=filename,
                Body=payload_image,
                ContentType='image/png',
                Metadata=metadata
            )
        except ClientError as e:
            print(f"Error uploading image: {e}")
            # Handle the error appropriately, such as logging the error or raising an exception
            raise  # Re-raise the exception if necessary

        # Get the image URL
        if self.access_url:
            image_url = f"{self.access_url}/{filename}"
        else:
            image_url = f"{self.access_url}/{self.bucket_name}/{filename}"

        return image_url
    
    @in_executor()
    def image_to_bytes(self, image: Image.Image, format="PNG"):
        """converts PIL.Image -> bytes"""
        buffer = BytesIO()
        image.save(buffer, format=format)
        return buffer.getvalue()
