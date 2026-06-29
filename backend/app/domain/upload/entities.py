import datetime

class UploadedFile:
    """已上传文件的领域实体"""
    def __init__(
        self,
        filename: str,
        file_path: str,
        file_size_mb: float,
        id: int = None,
        created_at: datetime.datetime = None
    ):
        self.id = id
        self.filename = filename
        self.file_path = file_path
        self.file_size_mb = file_size_mb
        self.created_at = created_at or datetime.datetime.now()

