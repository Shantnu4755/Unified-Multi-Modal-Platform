from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import os
import uuid
import logging
from typing import Optional, Any

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.config import settings
from app.models.document import Document, DocumentChunk
from app.models.user import User
from app.schemas.document import DocumentUploadResponse
from app.schemas.user import UserCreate, UserResponse, Token, LoginRequest
from app.services.document_service import DocumentService
from app.services.query_service import QueryService
from app.services.llm_service import LLMService
from app.auth.auth import (
    authenticate_user,
    create_access_token,
    get_password_hash,
    get_current_active_user,
    get_current_admin_user,
)

logger = logging.getLogger(__name__)


class HealthController:
    async def health(self) -> dict[str, Any]:
        return {
            "status": "healthy",
            "service": "rag-api",
            "timestamp": datetime.utcnow().isoformat(),
            "version": "1.0.0",
        }

    async def database_health(self) -> dict[str, Any]:
        return {
            "status": "healthy",
            "service": "database",
            "timestamp": datetime.utcnow().isoformat(),
        }


class DocumentsController:
    def __init__(self) -> None:
        self.document_service = DocumentService()
        self.query_service = QueryService()
        os.makedirs(settings.upload_dir, exist_ok=True)

        self.allowed_extensions = {".pdf", ".txt", ".doc", ".docx"}
        self.max_file_size = 50 * 1024 * 1024

    async def upload(self, file: UploadFile, db: Session, current_user: Optional[User]) -> DocumentUploadResponse:
        file_extension = Path(file.filename).suffix.lower()
        if file_extension not in self.allowed_extensions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File type {file_extension} not allowed. Allowed types: {', '.join(self.allowed_extensions)}",
            )

        content = await file.read()
        if len(content) > self.max_file_size:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File size {len(content)} exceeds maximum allowed size of {self.max_file_size} bytes",
            )

        unique_id = str(uuid.uuid4())
        filename = f"{unique_id}{file_extension}"
        file_path = os.path.join(settings.upload_dir, filename)

        with open(file_path, "wb") as f:
            f.write(content)

        db_document = Document(
            filename=filename,
            original_filename=file.filename,
            file_path=file_path,
            file_type=file_extension,
            file_size=len(content),
            status="uploaded",
            user_id=current_user.id if current_user else None,
        )

        db.add(db_document)
        db.commit()
        db.refresh(db_document)

        return DocumentUploadResponse(
            document_id=db_document.id,
            filename=db_document.original_filename,
            status=db_document.status,
            message="Document uploaded successfully",
        )

    async def list(self, db: Session):
        return db.query(Document).all()

    async def get(self, document_id: int, db: Session):
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
        return document

    async def process(self, document_id: int, db: Session):
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

        if document.status not in ["uploaded", "failed"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Document cannot be processed. Current status: {document.status}",
            )

        success = await self.document_service.process_document(document_id, db)
        if success:
            return {"message": "Document processing completed successfully", "document_id": document_id}
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Document processing failed")

    async def delete(self, document_id: int, db: Session):
        success = self.document_service.delete_document(document_id, db)
        if success:
            return {"message": "Document deleted successfully", "document_id": document_id}
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found or deletion failed")

    async def chunks(self, document_id: int, db: Session):
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

        chunks = self.document_service.get_document_chunks(document_id, db)
        return {
            "document_id": document_id,
            "total_chunks": len(chunks),
            "chunks": [
                {
                    "index": chunk.chunk_index,
                    "content": (chunk.content[:200] + "...") if len(chunk.content) > 200 else chunk.content,
                    "vector_id": chunk.vector_id,
                }
                for chunk in chunks
            ],
        }

    async def summary(self, document_id: int, db: Session):
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

        if document.status != "completed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Document must be processed before generating summary. Current status: {document.status}",
            )

        try:
            return await self.query_service.get_document_summary(document_id, db)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate summary: {str(e)}",
            )


class QueryController:
    def __init__(self) -> None:
        self.query_service = QueryService()

    async def query(self, request: Any, db: Session):
        if not request.question.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Question cannot be empty")

        logger.info(f"Processing query: {request.question[:100]}...")

        try:
            return await self.query_service.process_query(
                question=request.question,
                document_id=request.document_id,
                max_results=request.max_results,
                score_threshold=request.score_threshold,
                db=db,
            )
        except Exception as e:
            logger.error(f"Query processing failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Query processing failed: {str(e)}",
            )

    async def health(self):
        return {
            "status": "healthy",
            "service": "query-service",
            "components": {"embedding_service": "ready", "vector_database": "ready", "llm_service": "ready"},
        }


class ChatController:
    def __init__(self) -> None:
        self.llm_service = LLMService()

    async def chat(self, message: str) -> dict[str, Any]:
        if not message.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message cannot be empty")

        reply = self.llm_service.chat(message)
        return {"message": message, "reply": reply}


class AuthController:
    async def register(self, user_data: UserCreate, db: Session) -> UserResponse:
        existing_user = db.query(User).filter(User.email == user_data.email).first()
        if existing_user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

        hashed_password = get_password_hash(user_data.password)
        db_user = User(
            email=user_data.email,
            hashed_password=hashed_password,
            is_active=True,
            is_admin=False,
        )

        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user

    async def login(self, login_data: LoginRequest, db: Session) -> Token:
        user = authenticate_user(db, login_data.email, login_data.password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account is inactive")

        access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
        access_token = create_access_token(data={"sub": user.email}, expires_delta=access_token_expires)

        return {"access_token": access_token, "token_type": "bearer"}

    async def me(self, current_user: User = None) -> UserResponse:
        return current_user

    async def list_users(self, current_user: User, db: Session):
        return db.query(User).all()

    async def toggle_admin(self, user_id: int, current_user: User, db: Session):
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        user.is_admin = not user.is_admin
        db.commit()
        return {"message": f"User {user.email} admin status: {user.is_admin}"}

    async def delete_user(self, user_id: int, current_user: User, db: Session):
        if user_id == current_user.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete yourself")

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        db.delete(user)
        db.commit()
        return {"message": f"User {user.email} deleted successfully"}


class AdminController:
    def __init__(self) -> None:
        self.document_service = DocumentService()

    async def dashboard(self, current_user: User, db: Session):
        total_users = db.query(User).count()
        active_users = db.query(User).filter(User.is_active == True).count()
        admin_users = db.query(User).filter(User.is_admin == True).count()

        total_documents = db.query(Document).count()
        completed_documents = db.query(Document).filter(Document.status == "completed").count()
        processing_documents = db.query(Document).filter(Document.status == "processing").count()
        failed_documents = db.query(Document).filter(Document.status == "failed").count()

        total_chunks = db.query(DocumentChunk).count()
        total_storage = db.query(func.sum(Document.file_size)).scalar() or 0

        recent_documents = db.query(Document).order_by(Document.created_at.desc()).limit(5).all()

        return {
            "users": {
                "total": total_users,
                "active": active_users,
                "admin": admin_users,
                "inactive": total_users - active_users,
            },
            "documents": {
                "total": total_documents,
                "completed": completed_documents,
                "processing": processing_documents,
                "failed": failed_documents,
                "uploaded": total_documents - completed_documents - processing_documents - failed_documents,
            },
            "storage": {
                "total_size_bytes": total_storage,
                "total_chunks": total_chunks,
                "avg_chunks_per_doc": round(total_chunks / max(completed_documents, 1), 2),
            },
            "recent_documents": [
                {
                    "id": doc.id,
                    "filename": doc.original_filename,
                    "status": doc.status,
                    "created_at": doc.created_at,
                    "file_size": doc.file_size,
                }
                for doc in recent_documents
            ],
        }

    async def list_users(self, current_user: User, db: Session, skip: int = 0, limit: int = 100):
        users = db.query(User).offset(skip).limit(limit).all()
        total = db.query(User).count()
        return {"users": users, "total": total, "skip": skip, "limit": limit}

    async def toggle_user_active(self, user_id: int, current_user: User, db: Session):
        if user_id == current_user.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot modify your own account")

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        user.is_active = not user.is_active
        db.commit()
        return {
            "message": f"User {user.email} {'activated' if user.is_active else 'deactivated'}",
            "user_id": user_id,
            "is_active": user.is_active,
        }

    async def list_documents(self, current_user: User, db: Session, skip: int = 0, limit: int = 100, status_filter: Optional[str] = None):
        q = db.query(Document)
        if status_filter:
            q = q.filter(Document.status == status_filter)
        documents = q.offset(skip).limit(limit).all()
        total = q.count()
        return {"documents": documents, "total": total, "skip": skip, "limit": limit, "status_filter": status_filter}

    async def reprocess_document(self, document_id: int, current_user: User, db: Session):
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

        if document.status not in ["failed", "completed"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Cannot reprocess document with status: {document.status}")

        document.status = "uploaded"
        db.commit()
        return {"message": f"Document {document.original_filename} queued for reprocessing", "document_id": document_id}

    async def force_delete_document(self, document_id: int, current_user: User, db: Session):
        success = self.document_service.delete_document(document_id, db)
        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found or deletion failed")
        return {"message": f"Document {document_id} force deleted", "document_id": document_id}

    async def system_status(self, current_user: User, db: Session):
        try:
            db.execute("SELECT 1")
            db_status = "healthy"
        except Exception as e:
            db_status = f"error: {str(e)}"

        processing_stats = self.document_service.get_processing_stats(db)
        return {
            "database": {"status": db_status, "connection": "active"},
            "processing": processing_stats,
            "services": {"vector_database": "connected", "embedding_service": "ready", "llm_service": "ready"},
        }

    async def cleanup_orphaned_data(self, current_user: User, db: Session):
        orphaned_chunks = db.query(DocumentChunk).filter(~DocumentChunk.document_id.in_(db.query(Document.id))).all()
        orphaned_count = len(orphaned_chunks)

        for chunk in orphaned_chunks:
            db.delete(chunk)

        db.commit()
        return {"message": f"Cleanup completed. Removed {orphaned_count} orphaned chunks", "orphaned_chunks_removed": orphaned_count}
