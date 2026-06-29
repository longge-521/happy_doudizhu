import os
from fastapi import APIRouter, Response
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["Web"])

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

@router.get("/")
async def get_index():
    return {"status": "running", "service": "hmp_ws_service"}

@router.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)

