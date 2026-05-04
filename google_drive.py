"""
google_drive.py

Handles downloading a video from a Google Drive shareable link using gdown.
gdown automatically handles large-file confirmation pages so there is no
file-size limit on the caller's side.

Requirements:
    pip install gdown

Supported URL formats:
    https://drive.google.com/file/d/{FILE_ID}/view?usp=sharing
    https://drive.google.com/open?id={FILE_ID}
    https://drive.google.com/uc?id={FILE_ID}
    https://drive.google.com/uc?export=download&id={FILE_ID}
"""

import os
import re
import tempfile

try:
    import gdown
    GDOWN_AVAILABLE = True
except ImportError:
    GDOWN_AVAILABLE = False


# Regex patterns to extract the file ID from any Drive share URL
_DRIVE_PATTERNS = [
    r"/file/d/([a-zA-Z0-9_-]+)",   # /file/d/{ID}/view
    r"[?&]id=([a-zA-Z0-9_-]+)",    # ?id={ID} or &id={ID}
    r"/d/([a-zA-Z0-9_-]+)",        # short /d/{ID} form
]


def extract_file_id(url: str) -> str | None:
    """
    Extract the Google Drive file ID from a share URL.
    Returns None if the URL does not look like a Drive link.
    """
    for pattern in _DRIVE_PATTERNS:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def is_drive_url(url: str) -> bool:
    """Return True if the URL looks like a Google Drive share link."""
    return "drive.google.com" in url and extract_file_id(url) is not None


def download_drive_video(url: str) -> str:
    """
    Download a video from a Google Drive shareable link.

    The file must be shared as "anyone with the link can view" — private
    files require OAuth and cannot be downloaded this way.

    Returns the path to the downloaded temp file.
    Raises ValueError for bad URLs or missing gdown.
    Raises RuntimeError if the download fails.
    """
    if not GDOWN_AVAILABLE:
        raise RuntimeError(
            "gdown is not installed. Run: pip install gdown"
        )

    file_id = extract_file_id(url)
    if not file_id:
        raise ValueError(
            "Could not find a file ID in this URL. "
            "Make sure you're pasting a Google Drive share link."
        )

    # Build the canonical gdown URL
    download_url = f"https://drive.google.com/uc?id={file_id}"

    # Create a temp file — gdown needs the path, not a file handle
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".mp4")
    os.close(tmp_fd)

    try:
        output = gdown.download(
            download_url,
            output=tmp_path,
            quiet=True,
            fuzzy=True,          # handles extra URL params gracefully
        )

        if output is None or not os.path.exists(tmp_path) or os.path.getsize(tmp_path) == 0:
            raise RuntimeError(
                "Download failed. The file may be private or the link may have expired. "
                "Make sure sharing is set to 'anyone with the link can view'."
            )

        return tmp_path

    except Exception as exc:
        # Clean up the empty temp file if something went wrong
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise RuntimeError(f"Google Drive download error: {exc}") from exc
