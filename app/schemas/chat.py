from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID


# Thread Schemas
class ThreadCreate(BaseModel):
    title: Optional[str] = None
    system_instruction: str = Field(..., min_length=1)


class ThreadUpdate(BaseModel):
    title: Optional[str] = None
    system_instruction: Optional[str] = None


class ThreadResponse(BaseModel):
    id: UUID
    user_id: UUID
    title: Optional[str]
    system_instruction: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Message Schemas
class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1)


class MessageResponse(BaseModel):
    id: UUID
    thread_id: UUID
    role: str
    content: str
    audio_url: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# Chat Request Schemas
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    thread_id: Optional[UUID] = None
    audio_base64: Optional[str] = Field(None, description="Base64 encoded audio data")


# Thread with Messages
class ThreadWithMessages(BaseModel):
    thread: ThreadResponse
    messages: List[MessageResponse]
