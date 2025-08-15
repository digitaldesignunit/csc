from fastapi import APIRouter, Request
from pymongo.errors import PyMongoError

router = APIRouter()


@router.get("/health/db", summary="Check MongoDB connection")
async def health_check_db(request: Request):
    try:
        await request.app.mongodb.command("ping")
        return {"ok": True}
    except PyMongoError as e:
        return {"ok": False, "error": str(e)}
