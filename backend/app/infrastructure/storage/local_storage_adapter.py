import logging
import os
import re
import shutil
import time
from typing import List, Union

logger = logging.getLogger("hmp_ws_service")


class LocalStorageAdapter:
    """Local disk storage for chunked uploads and merged files."""

    MAX_CHUNK_BYTES = int(os.getenv("UPLOAD_MAX_CHUNK_BYTES", str(4 * 1024 * 1024)))
    MAX_UPLOAD_BYTES = int(os.getenv("UPLOAD_MAX_BYTES", str(512 * 1024 * 1024)))
    MAX_TOTAL_CHUNKS = max(1, (MAX_UPLOAD_BYTES + MAX_CHUNK_BYTES - 1) // MAX_CHUNK_BYTES)

    def __init__(self):
        self.base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        self.upload_dir = os.getenv("UPLOAD_DIR", os.path.join(self.base_dir, "uploads"))
        self.temp_dir = os.getenv("TEMP_DIR", os.path.join(self.base_dir, "temp_uploads"))
        self._ensure_dirs()

    def _ensure_dirs(self):
        for directory in [self.upload_dir, self.temp_dir]:
            if not os.path.exists(directory):
                os.makedirs(directory)

    def secure_filename(self, filename: str) -> str:
        filename = os.path.basename(filename)
        filename = re.sub(r"[^\w\u4e00-\u9fff.\-]", "_", filename)
        return filename.strip() or "unnamed_file"

    def _validate_upload_id(self, upload_id: str):
        if not upload_id or not isinstance(upload_id, str):
            raise ValueError("Invalid upload_id type")
        if not re.match(r"^[a-zA-Z0-9_\-\.]+$", upload_id):
            raise ValueError("upload_id contains invalid characters")
        if len(upload_id) < 5 or len(upload_id) > 150:
            raise ValueError("upload_id length is out of range")

    def _validate_chunk_index(self, chunk_index: int):
        if not isinstance(chunk_index, int) or chunk_index < 0 or chunk_index >= self.MAX_TOTAL_CHUNKS:
            raise ValueError("chunk_index is out of range")

    def _validate_chunk_size(self, data: Union[bytes, memoryview]):
        if len(data) > self.MAX_CHUNK_BYTES:
            raise ValueError("chunk size exceeds limit")

    def _validate_total_chunks(self, total_chunks: int):
        if not isinstance(total_chunks, int) or total_chunks < 1 or total_chunks > self.MAX_TOTAL_CHUNKS:
            raise ValueError("total_chunks is out of range")

    def get_temp_upload_dir(self, upload_id: str) -> str:
        self._validate_upload_id(upload_id)
        temp_dir_abs = os.path.abspath(self.temp_dir)
        target_dir_abs = os.path.abspath(os.path.join(temp_dir_abs, f"tmp_{upload_id}"))
        if not target_dir_abs.startswith(temp_dir_abs + os.path.sep):
            raise ValueError("Path traversal detected in upload_id")
        return target_dir_abs

    def get_upload_file_path(self, filename: str) -> str:
        return os.path.join(self.upload_dir, self.secure_filename(filename))

    def save_chunk(self, upload_id: str, chunk_index: int, data: Union[bytes, memoryview]):
        self._validate_chunk_index(chunk_index)
        self._validate_chunk_size(data)

        temp_upload_dir = self.get_temp_upload_dir(upload_id)
        if not os.path.exists(temp_upload_dir):
            os.makedirs(temp_upload_dir)

        chunk_file_path = os.path.join(temp_upload_dir, str(chunk_index))
        with open(chunk_file_path, "wb") as f:
            f.write(data)

    def get_completed_chunks(self, upload_id: str) -> List[int]:
        temp_upload_dir = self.get_temp_upload_dir(upload_id)
        completed_chunks = []
        if os.path.exists(temp_upload_dir):
            for fname in os.listdir(temp_upload_dir):
                if fname.isdigit():
                    completed_chunks.append(int(fname))
            completed_chunks.sort()
        return completed_chunks

    def merge_chunks(self, upload_id: str, filename: str, total_chunks: int) -> str:
        self._validate_total_chunks(total_chunks)

        temp_upload_dir = self.get_temp_upload_dir(upload_id)
        file_path = self.get_upload_file_path(filename)

        try:
            for i in range(total_chunks):
                chunk_path = os.path.join(temp_upload_dir, str(i))
                if not os.path.exists(chunk_path):
                    raise FileNotFoundError(f"Chunk {i} is missing, cannot merge")

            with open(file_path, "wb") as target_file:
                for i in range(total_chunks):
                    chunk_path = os.path.join(temp_upload_dir, str(i))
                    with open(chunk_path, "rb") as source_file:
                        shutil.copyfileobj(source_file, target_file, length=256 * 1024)
            return file_path
        finally:
            temp_dir_abs = os.path.abspath(self.temp_dir)
            if os.path.basename(temp_upload_dir).startswith("tmp_") and temp_upload_dir.startswith(temp_dir_abs):
                shutil.rmtree(temp_upload_dir, ignore_errors=True)

    def abort_upload(self, upload_id: str):
        temp_upload_dir = self.get_temp_upload_dir(upload_id)
        temp_dir_abs = os.path.abspath(self.temp_dir)
        if os.path.basename(temp_upload_dir).startswith("tmp_") and temp_upload_dir.startswith(temp_dir_abs):
            shutil.rmtree(temp_upload_dir, ignore_errors=True)

    def cleanup_stale_uploads(self, timeout_hours: float = 2.0) -> int:
        now = time.time()
        timeout_seconds = timeout_hours * 3600
        cleaned = 0
        try:
            if not os.path.exists(self.temp_dir):
                return 0
            for dirname in os.listdir(self.temp_dir):
                if not dirname.startswith("tmp_"):
                    continue
                dirpath = os.path.join(self.temp_dir, dirname)
                if not os.path.isdir(dirpath):
                    continue
                try:
                    if now - os.path.getmtime(dirpath) > timeout_seconds:
                        shutil.rmtree(dirpath, ignore_errors=True)
                        cleaned += 1
                        logger.info(f"Cleaned up stale temp upload: {dirname}")
                except OSError:
                    pass
        except Exception as e:
            logger.error(f"Error scanning temp uploads: {e}")
        return cleaned
