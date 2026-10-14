"""System One image contract, compatible with JevLink's top-level images."""
import base64
import binascii
import re

MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_TOTAL_BYTES = 8 * 1024 * 1024
MAX_REQUEST_BYTES = 13 * 1024 * 1024
MEDIA_TYPES = ('image/png', 'image/jpeg', 'image/webp')


def validate_images(images):
    if not isinstance(images, list) or len(images) > 4:
        raise ValueError('images must be a list of at most 4 images')
    total = 0
    for item in images:
        if isinstance(item, str):
            match = re.fullmatch(r'data:(image/(?:png|jpeg|webp));base64,(.+)', item)
            if not match:
                raise ValueError('Image must be a PNG/JPEG/WebP Base64 Data URL')
            encoded = match[2]
        elif (isinstance(item, dict) and set(item) == {'mediaType', 'base64'}
              and item['mediaType'] in MEDIA_TYPES and isinstance(item['base64'], str)):
            encoded = item['base64']
        else:
            raise ValueError('Invalid image object')
        if len(encoded) > ((MAX_IMAGE_BYTES + 2) // 3) * 4:
            raise ValueError('Image exceeds 4 MiB')
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError('Invalid standard Base64 image') from None
        if not raw or base64.b64encode(raw).decode('ascii') != encoded:
            raise ValueError('Image requires nonempty canonical Base64')
        if len(raw) > MAX_IMAGE_BYTES:
            raise ValueError('Image exceeds 4 MiB')
        total += len(raw)
    if total > MAX_TOTAL_BYTES:
        raise ValueError('Images exceed 8 MiB in total')


def png_data_url(raw):
    return 'data:image/png;base64,' + base64.b64encode(raw).decode('ascii')
