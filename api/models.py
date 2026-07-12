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
    workspace_id: Optional[str] = None
    workflow_id: Optional[str] = None

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
    summary: Optional[str] = None
    confidence: Optional[float] = None
    verification: Optional[Any] = None
    findings: List[Any] = []
    report: Optional[Any] = None
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

# Missions (workforce layer)
class MissionRequest(BaseModel):
    instruction: str
    workspace_id: Optional[str] = None
    workflow_id: Optional[str] = None

# Organizations
class OrgCreateRequest(BaseModel):
    name: str

class MemberAddRequest(BaseModel):
    email: EmailStr
    role: str = "member"

class MemberUpdateRequest(BaseModel):
    role: str

class WorkspaceCreateRequest(BaseModel):
    name: str
    description: str = ""
    environment: str = "production"

class WorkspaceUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    environment: Optional[str] = None
    policy: Optional[dict] = None

class SecretCreateRequest(BaseModel):
    name: str
    value: str
    workspace_id: Optional[str] = None

class WorkspaceWebhookRequest(BaseModel):
    url: Optional[str] = None  # https URL, or empty/None to clear

class WorkspaceEgressRequest(BaseModel):
    """What may leave this workspace's machines. Policy as data."""
    mode: str = "allow"                 # allow | redact | local_only | deny
    redact: List[str] = []              # redaction classes (redact mode)
    custom_patterns: List[str] = []     # customer-supplied regexes

class WorkspaceLearningRequest(BaseModel):
    """What PerceptAI may learn from this workspace's executions. Policy as
    data; changing it appends immutable consent rows."""
    tiers: dict = {}                    # {workspace_only, anonymized_priors, model_improvement}
    anonymization: Optional[str] = None  # standard | strict

# Workflows (Agent Studio)
class WorkflowCreateRequest(BaseModel):
    name: str
    description: str = ""
    instruction: str = ""
    variables: List[dict] = []
    mode: str = "task"
    policy: dict = {}
    workspace_id: Optional[str] = None
    template_id: Optional[str] = None  # seed from the template gallery

class WorkflowUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    instruction: Optional[str] = None
    variables: Optional[List[dict]] = None
    mode: Optional[str] = None
    policy: Optional[dict] = None
    schedule: Optional[dict] = None
    status: Optional[str] = None  # draft | published | archived

class WorkflowRenderRequest(BaseModel):
    values: dict = {}

# Approvals
class ApprovalDecisionRequest(BaseModel):
    decision: str  # approved | denied
    reason: str = ""

# Dashboard
class DashboardResponse(BaseModel):
    total_sessions: int
    successful_sessions: int
    failed_sessions: int
    total_executions_this_month: int
    executions_limit: int
    recent_sessions: List[SessionSummary]
    plan: str