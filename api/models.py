from pydantic import BaseModel, EmailStr
from typing import Optional, List, Any
from datetime import datetime

# Auth
class SignUpRequest(BaseModel):
    email: EmailStr
    password: str

class SignInRequest(BaseModel):
    email: EmailStr
    password: str

class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str

# API Keys
class CreateKeyRequest(BaseModel):
    name: Optional[str] = "Default Key"

class APIKeyResponse(BaseModel):
    id: str
    key_prefix: str
    name: str
    is_active: bool
    last_used_at: Optional[datetime]
    created_at: datetime

class NewAPIKeyResponse(APIKeyResponse):
    full_key: str  # Only shown once on creation

# Task Execution
class ExecuteRequest(BaseModel):
    instruction: str
    context: Optional[str] = None

class ExecutionStep(BaseModel):
    step_number: int
    description: str
    action: str
    status: str  # pending, running, completed, failed
    result: Optional[Any] = None
    timestamp: Optional[datetime] = None

class ExecuteResponse(BaseModel):
    session_id: str
    status: str
    instruction: str
    steps: List[ExecutionStep] = []
    execution_time: Optional[float] = None
    error: Optional[str] = None
    created_at: datetime

# Session History
class SessionSummary(BaseModel):
    id: str
    instruction: str
    status: str
    execution_time: Optional[float]
    steps_count: int
    created_at: datetime

class SessionDetail(SessionSummary):
    steps: List[ExecutionStep]
    result: Optional[Any]
    error: Optional[str]

# Usage
class UsageResponse(BaseModel):
    month: str
    executions_used: int
    executions_limit: int
    plan: str
    percentage_used: float

# Dashboard
class DashboardResponse(BaseModel):
    total_sessions: int
    successful_sessions: int
    failed_sessions: int
    total_executions_this_month: int
    executions_limit: int
    recent_sessions: List[SessionSummary]
    plan: str