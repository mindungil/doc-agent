from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class DocumentBase(BaseModel):
    title: str
    filename: str


class DocumentCreate(DocumentBase):
    pass


class Document(DocumentBase):
    id: int
    status: str
    uploaded_at: datetime
    assigned_to: Optional[str] = None
    assigned_at: Optional[datetime] = None
    is_auto_assigned: bool = False
    
    class Config:
        from_attributes = True


class EmployeeCandidate(BaseModel):
    name: str
    rank: str
    dept1: str
    dept2: Optional[str] = ""
    dept3: Optional[str] = ""
    tasks: str
    phone: Optional[str] = None
    score: Optional[float] = None


class AssignmentRecommendation(BaseModel):
    primary: EmployeeCandidate
    candidates: List[EmployeeCandidate]
    reasoning: str


class DocumentDetail(Document):
    content_preview: Optional[str] = None
    recommendation: Optional[AssignmentRecommendation] = None


class AssignmentRequest(BaseModel):
    document_id: int
    employee_name: str
    employee_dept: str
    is_auto: bool = False


class StatsResponse(BaseModel):
    total_documents_today: int
    assigned_count: int
    auto_assigned_count: int
    manual_assigned_count: int


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    success: bool
    message: str
    user: Optional[str] = None


class AuthStatus(BaseModel):
    authenticated: bool
    username: Optional[str] = None
