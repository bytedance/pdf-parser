import base64


def _is_image_valid(img_data: bytes) -> tuple[bool, str]:
    """
    Check if the image data is valid.

    Args:
        img_data: The raw image data.

    Returns:
        is_valid: True if the image is valid, False otherwise.
        img_format: The type of the image (e.g., 'png', 'jpeg', 'gif', 'bmp').
    """
    # Check for minimum size to be considered a valid image
    if len(img_data) < 100:
        return False, ""

    # Check image header
    headers = {
        b"\xff\xd8\xff": "jpeg",  # JPEG
        b"\x89\x50\x4e\x47": "png",  # PNG
        b"\x47\x49\x46": "gif",  # GIF
        b"\x42\x4d": "bmp",  # BMP
    }
    for header, format in headers.items():
        if img_data.startswith(header):
            return True, format
    return False, ""


def embedded_image_markdown(img_data: bytes, alt_text: str = "") -> tuple[str, str]:
    """
    Convert image data to markdown with embedded format.

    Args:
        img_data: The raw image data.
        alt_text: Alternative text for the image.
                  Currently, this is the ocr text for textin.

    Returns:
        image_content: in markdown base64
        image_format: The type of the image (e.g., 'png', 'jpeg', 'gif', 'bmp').
    """
    is_valid, img_format = _is_image_valid(img_data)
    if not is_valid:
        return "", ""
    try:
        base64_data = base64.b64encode(img_data).decode("utf-8")
        return (
            f"![{alt_text}](data:image/{img_format};base64,{base64_data})",
            img_format,
        )
    except Exception as e:
        raise Exception("Error converting image to base64") from e
