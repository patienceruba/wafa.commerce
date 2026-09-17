from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from config.database import get_db
from users.models import User
from services.assistant_service import AssistantService

router = APIRouter(prefix="/assistant", tags=["assistant"])


def get_assistant_service(db: Session = Depends(get_db)) -> AssistantService:
    return AssistantService(db)


class ChatQueryRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatQueryResponse(BaseModel):
    reply: str
    products: List[Dict[str, Any]] = []
    order: Optional[Dict[str, Any]] = None
    suggestions: List[str] = []


@router.post("/chat", response_model=ChatQueryResponse)
def assistant_chat(
    payload: ChatQueryRequest,
    assistant_service: AssistantService = Depends(get_assistant_service),
):
    """
    Live database-aware AI concierge endpoint.
    Queries active inventory, pricing, stock levels, orders, reviews, and categories.
    """
    result = assistant_service.process_query(query_text=payload.message)
    return result
