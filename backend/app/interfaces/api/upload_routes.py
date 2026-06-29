import os
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.infrastructure.database.session import get_db
from app.infrastructure.database import SQLUploadedFileRepository
from app.infrastructure.database.models import UploadedFileORM
from app.infrastructure.auth import verify_token
from app.infrastructure.audit_route import AuditLogRoute

logger = logging.getLogger("hmp_ws_service")
router = APIRouter(
    prefix="/api/uploads",
    tags=["Uploads"],
    dependencies=[Depends(verify_token)],
    route_class=AuditLogRoute
)

@router.get("", summary="QUERY_UPLOADED_FILES", description="uploaded_file")
async def get_uploaded_files(db: Session = Depends(get_db)):
    try:
        repo = SQLUploadedFileRepository(db)
        files = repo.find_all()
        result = []
        for f in files:
            result.append({
                "id": f.id,
                "filename": f.filename,
                "file_path": f.file_path,
                "file_size_mb": f.file_size_mb,
                "created_at": f.created_at.strftime("%Y-%m-%d %H:%M:%S") if f.created_at else ""
            })
        return result
    except Exception as e:
        logger.error(f"Failed to fetch uploaded files API: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch uploaded files")

@router.delete("/{file_id}", summary="DELETE_FILE", description="uploaded_file")
async def delete_uploaded_file(request: Request,
                               file_id: int,
                               db: Session = Depends(get_db)):
    filename = "unknown"
    repo = SQLUploadedFileRepository(db)
    # 1. 查找文件记录
    orm_file = db.query(UploadedFileORM).filter(UploadedFileORM.id == file_id).first()
    if not orm_file:
        raise HTTPException(status_code=404, detail="File record not found")
        
    file_path = orm_file.file_path
    filename = orm_file.filename
    
    # 2. 安全防范：路径穿越验证，确保只允许删除合法的 uploads 目录下的文件
    # 允许的合法目录集合（包含当前配置的 UPLOAD_DIR 和项目默认的内部 uploads 目录）
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    default_upload_dir = os.path.join(base_dir, "uploads")
    config_upload_dir = os.getenv("UPLOAD_DIR", default_upload_dir)
    
    # 规范化并获取绝对路径，若为相对路径则相对于项目的 base_dir
    allowed_dirs = [
        os.path.abspath(default_upload_dir),
        os.path.abspath(os.path.join(base_dir, config_upload_dir) if not os.path.isabs(config_upload_dir) else config_upload_dir)
    ]
    
    # 处理待删除的文件物理路径
    file_path_abs = os.path.abspath(os.path.join(allowed_dirs[0], file_path) if not os.path.isabs(file_path) else file_path)
    
    # 归一化路径（解析符号链接并统一 Windows 大小写与斜杠）
    file_path_norm = os.path.normcase(os.path.realpath(file_path_abs))
    
    is_safe = False
    for ad in allowed_dirs:
        ad_norm = os.path.normcase(os.path.realpath(ad))
        try:
            # 使用 commonpath 确保 file_path_norm 是 ad_norm 的子路径（排除了 uploads_other 等偏门字符匹配漏洞）
            common = os.path.commonpath([ad_norm, file_path_norm])
            if os.path.normcase(common) == ad_norm and file_path_norm != ad_norm:
                is_safe = True
                break
        except ValueError:
            continue
            
    if not is_safe:
        logger.warning(f"Path traversal deletion block! Attempted path: {file_path}")
        raise HTTPException(status_code=403, detail="Forbidden: Deletion target path traversal blocked")
        
    # 3. 物理文件删除
    if os.path.exists(file_path_abs):
        try:
            os.remove(file_path_abs)
            logger.info(f"Physical file deleted: {file_path_abs}")
        except Exception as fe:
            logger.error(f"Failed to delete physical file {file_path_abs}: {fe}")
            raise HTTPException(status_code=500, detail=f"Failed to delete physical file: {fe}")
    else:
        logger.warning(f"Physical file missing during deletion: {file_path_abs}")
        
    # 4. 数据库记录移除
    repo.delete_by_id(file_id)
    
    return {"status": "success", "message": f"文件 '{filename}' 及其数据库记录已删除成功"}

