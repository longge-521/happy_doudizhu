import os
from fastapi import APIRouter, Response
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["Web"])

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

@router.get("/")
async def get_index():
    # 尝试托管前端打包页面
    frontend_dist_index = os.path.join(os.path.dirname(BASE_DIR), "frontend", "dist", "index.html")
    if os.path.exists(frontend_dist_index):
        with open(frontend_dist_index, "r", encoding="utf-8") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content)
    return {"status": "running", "service": "happy_doudizhu"}

@router.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)

