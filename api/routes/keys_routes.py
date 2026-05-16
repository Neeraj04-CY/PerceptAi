from fastapi import APIRouter, Depends, HTTPException
from models import CreateKeyRequest, APIKeyResponse, NewAPIKeyResponse
from auth import get_current_user, generate_api_key
from database import get_service_db
from datetime import datetime, timezone

router = APIRouter(prefix="/keys", tags=["api-keys"])

@router.get("", response_model=list[APIKeyResponse])
async def list_keys(current_user: dict = Depends(get_current_user)):
    db = get_service_db()
    result = db.table("api_keys").select("*").eq(
        "user_id", current_user["sub"]
    ).execute()
    return result.data or []

@router.post("", response_model=NewAPIKeyResponse)
async def create_key(
    body: CreateKeyRequest,
    current_user: dict = Depends(get_current_user)
):
    db = get_service_db()
    full_key, key_hash, key_prefix = generate_api_key()
    
    result = db.table("api_keys").insert({
        "user_id": current_user["sub"],
        "key_hash": key_hash,
        "key_prefix": key_prefix,
        "name": body.name
    }).execute()
    
    data = result.data[0]
    
    return NewAPIKeyResponse(
        id=data["id"],
        key_prefix=key_prefix,
        name=data["name"],
        is_active=data["is_active"],
        last_used_at=data.get("last_used_at"),
        created_at=data["created_at"],
        full_key=full_key
    )

@router.delete("/{key_id}")
async def delete_key(
    key_id: str,
    current_user: dict = Depends(get_current_user)
):
    db = get_service_db()
    db.table("api_keys").update({"is_active": False}).eq(
        "id", key_id
    ).eq("user_id", current_user["sub"]).execute()
    return {"message": "Key deactivated"}