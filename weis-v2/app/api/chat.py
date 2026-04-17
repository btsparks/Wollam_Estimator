"""Chat API — FastAPI routes for AI Estimating Chat.

Thin wrapper over the chat service. All business logic lives
in app/services/chat.py.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.chat import (
    send_message,
    list_conversations,
    get_conversation,
    delete_conversation,
    get_data_summary,
)

router = APIRouter(prefix="/api/chat", tags=["chat"])


# ── Pydantic models ──

class SendMessageRequest(BaseModel):
    conversation_id: int | None = None
    message: str
    bid_id: int | None = None  # Optional: active bid context for vector search


# ── Routes ──

@router.post("/send")
def chat_send(req: SendMessageRequest):
    """Send a message to the AI estimating assistant.

    If conversation_id is null, creates a new conversation.
    Returns the AI response with source citations.
    """
    if not req.message or not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    try:
        result = send_message(req.conversation_id, req.message.strip(), bid_id=req.bid_id)
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process message: {str(e)}",
        )


@router.get("/conversations")
def chat_list_conversations(bid_id: Optional[int] = Query(None)):
    """Return conversations, most recent first. Filter by bid_id if provided."""
    try:
        return list_conversations(bid_id=bid_id)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load conversations: {str(e)}",
        )


@router.get("/conversations/{conversation_id}")
def chat_get_conversation(conversation_id: int):
    """Return a full conversation with all messages."""
    try:
        result = get_conversation(conversation_id)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load conversation: {str(e)}",
        )
    if not result:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return result


@router.delete("/conversations/{conversation_id}")
def chat_delete_conversation(conversation_id: int):
    """Delete a conversation and all its messages."""
    try:
        deleted = delete_conversation(conversation_id)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete conversation: {str(e)}",
        )
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"ok": True}


@router.get("/data-summary")
def chat_data_summary():
    """Return a summary of available data for the chat UI.

    Shows estimators what data is available to query against.
    """
    try:
        return get_data_summary()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load data summary: {str(e)}",
        )
