from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List

from app.database import get_db
from app.auth.auth import (
    get_current_user_optional,
    get_current_active_user,
    get_current_admin_user,
)
from app.models.user import User
from app.controllers import (
    HealthController,
    DocumentsController,
    QueryController,
    ChatController,
    AuthController,
    AdminController,
)
from app.schemas.user import UserCreate, LoginRequest

router = APIRouter()

health_controller = HealthController()
documents_controller = DocumentsController()
query_controller = QueryController()
chat_controller = ChatController()
auth_controller = AuthController()
admin_controller = AdminController()


class QueryRequest(BaseModel):
    question: str
    document_id: Optional[int] = None
    max_results: Optional[int] = 5
    score_threshold: Optional[float] = 0.7


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    message: str
    reply: str


class SourceInfo(BaseModel):
    document_id: int
    chunk_index: int
    content: str
    score: float
    filename: Optional[str] = None
    file_type: Optional[str] = None


class QueryResponse(BaseModel):
    question: str
    answer: str
    sources: List[SourceInfo]
    processing_time_ms: int


@router.get("/health")
async def health_check():
    return await health_controller.health()


@router.get("/health/db")
async def database_health():
    return await health_controller.database_health()


@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    return await documents_controller.upload(file=file, db=db, current_user=current_user)


@router.get("/documents")
async def list_documents(db: Session = Depends(get_db)):
    return await documents_controller.list(db=db)


@router.get("/documents/{document_id}")
async def get_document(document_id: int, db: Session = Depends(get_db)):
    return await documents_controller.get(document_id=document_id, db=db)


@router.post("/documents/{document_id}/process")
async def process_document(document_id: int, db: Session = Depends(get_db)):
    return await documents_controller.process(document_id=document_id, db=db)


@router.delete("/documents/{document_id}")
async def delete_document(document_id: int, db: Session = Depends(get_db)):
    return await documents_controller.delete(document_id=document_id, db=db)


@router.get("/documents/{document_id}/chunks")
async def get_document_chunks(document_id: int, db: Session = Depends(get_db)):
    return await documents_controller.chunks(document_id=document_id, db=db)


@router.get("/documents/{document_id}/summary")
async def get_document_summary(document_id: int, db: Session = Depends(get_db)):
    return await documents_controller.summary(document_id=document_id, db=db)


@router.post("/query/", response_model=QueryResponse)
async def query_documents(request: QueryRequest, db: Session = Depends(get_db)):
    return await query_controller.query(request=request, db=db)


@router.post("/chat", response_model=ChatResponse)
async def general_chat(request: ChatRequest):
    return await chat_controller.chat(message=request.message)


@router.get("/query/health")
async def query_health():
    return await query_controller.health()


@router.post("/auth/register")
async def register(user_data: UserCreate, db: Session = Depends(get_db)):
    return await auth_controller.register(user_data=user_data, db=db)


@router.post("/auth/login")
async def login(login_data: LoginRequest, db: Session = Depends(get_db)):
    return await auth_controller.login(login_data=login_data, db=db)


@router.get("/auth/me")
async def me(current_user: User = Depends(get_current_active_user)):
    return await auth_controller.me(current_user=current_user)


@router.get("/auth/users")
async def list_users(current_user: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    return await auth_controller.list_users(current_user=current_user, db=db)


@router.put("/auth/users/{user_id}/admin")
async def toggle_admin_status(
    user_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    return await auth_controller.toggle_admin(user_id=user_id, current_user=current_user, db=db)


@router.delete("/auth/users/{user_id}")
async def delete_user(
    user_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    return await auth_controller.delete_user(user_id=user_id, current_user=current_user, db=db)


@router.get("/admin/dashboard")
async def admin_dashboard(current_user: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    return await admin_controller.dashboard(current_user=current_user, db=db)


@router.get("/admin/users")
async def admin_list_users(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
):
    return await admin_controller.list_users(current_user=current_user, db=db, skip=skip, limit=limit)


@router.put("/admin/users/{user_id}/toggle-active")
async def admin_toggle_user_active(user_id: int, current_user: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    return await admin_controller.toggle_user_active(user_id=user_id, current_user=current_user, db=db)


@router.get("/admin/documents")
async def admin_list_documents(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
):
    return await admin_controller.list_documents(current_user=current_user, db=db, skip=skip, limit=limit, status_filter=status)


@router.post("/admin/documents/{document_id}/reprocess")
async def admin_reprocess_document(document_id: int, current_user: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    return await admin_controller.reprocess_document(document_id=document_id, current_user=current_user, db=db)


@router.delete("/admin/documents/{document_id}/force")
async def admin_force_delete_document(document_id: int, current_user: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    return await admin_controller.force_delete_document(document_id=document_id, current_user=current_user, db=db)


@router.get("/admin/system/status")
async def admin_system_status(current_user: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    return await admin_controller.system_status(current_user=current_user, db=db)


@router.post("/admin/system/cleanup")
async def admin_cleanup(current_user: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    return await admin_controller.cleanup_orphaned_data(current_user=current_user, db=db)
