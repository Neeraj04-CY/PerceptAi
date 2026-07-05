from fastapi import APIRouter, HTTPException, Depends
from models import SignUpRequest, SignInRequest, AuthResponse
from auth import hash_password, verify_password, create_token
from database import get_service_db
import uuid

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/signup", response_model=AuthResponse)
async def signup(body: SignUpRequest):
    db = get_service_db()
    
    # Check if email exists
    existing = db.table("users").select("id").eq("email", body.email).execute()
    if existing.data:
        raise HTTPException(400, "Email already registered")
    
    # Validate password
    if len(body.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    
    # Create user
    user_id = str(uuid.uuid4())
    password_hash = hash_password(body.password)
    
    db.table("users").insert({
        "id": user_id,
        "email": body.email,
        "password_hash": password_hash
    }).execute()
    
    # Create free plan
    db.table("user_plans").insert({
        "user_id": user_id,
        "plan_id": "free"
    }).execute()
    
    # Create default API key
    from auth import generate_api_key
    full_key, key_hash, key_prefix = generate_api_key()
    
    db.table("api_keys").insert({
        "user_id": user_id,
        "key_hash": key_hash,
        "key_prefix": key_prefix,
        "name": "Default Key"
    }).execute()
    
    # Bootstrap the personal organization + default workspace. Best-effort:
    # a database without the platform migration still gets a working account
    # (the org is created lazily on first platform request instead).
    try:
        from orgs import ensure_personal_org
        ensure_personal_org(db, user_id, body.email)
    except Exception:
        pass

    token = create_token(user_id, body.email)

    return AuthResponse(
        access_token=token,
        user_id=user_id,
        email=body.email
    )

@router.post("/signin", response_model=AuthResponse)
async def signin(body: SignInRequest):
    db = get_service_db()
    
    result = db.table("users").select("*").eq("email", body.email).execute()
    
    if not result.data:
        raise HTTPException(401, "Invalid credentials")
    
    user = result.data[0]
    
    if not verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Invalid credentials")
    
    token = create_token(user["id"], user["email"])
    
    return AuthResponse(
        access_token=token,
        user_id=user["id"],
        email=user["email"]
    )

@router.get("/me")
async def me(current_user: dict = Depends(lambda: None)):
    from fastapi import Security
    from auth import get_current_user
    return current_user