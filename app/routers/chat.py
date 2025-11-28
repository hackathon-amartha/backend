import json
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, Header
from fastapi.responses import StreamingResponse
from supabase import Client

from app.database import get_supabase
from app.schemas.chat import (
    ThreadCreate,
    ThreadUpdate,
    ThreadResponse,
    MessageResponse,
    ThreadWithMessages,
    ChatRequest,
)
from app.services.thread import get_thread_service, ThreadService
from app.services.gemini import get_gemini_service, GeminiService

router = APIRouter(prefix="/chat", tags=["chat"])


async def get_current_user_id(
    authorization: str = Header(..., description="Bearer token")
) -> UUID:
    """Extract and verify user from JWT token"""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    token = authorization.replace("Bearer ", "")

    try:
        supabase: Client = get_supabase()
        user = supabase.auth.get_user(token)
        if not user or not user.user:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        return UUID(user.user.id)
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")


# Thread endpoints
@router.post("/threads", response_model=ThreadResponse, status_code=201)
async def create_thread(
    thread_data: ThreadCreate,
    user_id: UUID = Depends(get_current_user_id),
    thread_service: ThreadService = Depends(get_thread_service),
):
    """Create a new chat thread"""
    thread = await thread_service.create_thread(
        user_id=user_id,
        system_instruction=thread_data.system_instruction,
        title=thread_data.title,
    )
    if not thread:
        raise HTTPException(status_code=500, detail="Failed to create thread")
    return thread


@router.get("/threads", response_model=list[ThreadResponse])
async def get_threads(
    user_id: UUID = Depends(get_current_user_id),
    thread_service: ThreadService = Depends(get_thread_service),
):
    """Get all threads for the current user"""
    return await thread_service.get_user_threads(user_id)


@router.get("/threads/{thread_id}", response_model=ThreadWithMessages)
async def get_thread(
    thread_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    thread_service: ThreadService = Depends(get_thread_service),
):
    """Get a thread with all its messages"""
    thread = await thread_service.get_thread(thread_id, user_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    messages = await thread_service.get_thread_messages(thread_id)
    return {"thread": thread, "messages": messages}


@router.patch("/threads/{thread_id}", response_model=ThreadResponse)
async def update_thread(
    thread_id: UUID,
    thread_data: ThreadUpdate,
    user_id: UUID = Depends(get_current_user_id),
    thread_service: ThreadService = Depends(get_thread_service),
):
    """Update a thread's title or system instruction"""
    thread = await thread_service.update_thread(
        thread_id=thread_id,
        user_id=user_id,
        title=thread_data.title,
        system_instruction=thread_data.system_instruction,
    )
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    return thread


@router.delete("/threads/{thread_id}", status_code=204)
async def delete_thread(
    thread_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    thread_service: ThreadService = Depends(get_thread_service),
):
    """Delete a thread and all its messages"""
    deleted = await thread_service.delete_thread(thread_id, user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Thread not found")
    return None


# Chat endpoint with streaming
@router.post("/send")
async def send_message(
    message: str = Form(...),
    thread_id: Optional[str] = Form(None),
    audio: Optional[UploadFile] = File(None),
    user_id: UUID = Depends(get_current_user_id),
    thread_service: ThreadService = Depends(get_thread_service),
    gemini_service: GeminiService = Depends(get_gemini_service),
):
    """
    Send a message and get streaming response via SSE.

    - If thread_id is provided: continues existing conversation
    - If thread_id is not provided: creates a new thread

    Supports both text and audio input.
    Thread title is auto-generated for new threads.
    """
    from app.config import SYSTEM_INSTRUCTION

    is_new_thread = thread_id is None
    history = []
    thread = None

    if thread_id:
        # Existing thread - get context
        thread_uuid = UUID(thread_id)
        thread = await thread_service.get_thread(thread_uuid, user_id)
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")

        # Get conversation history
        messages = await thread_service.get_thread_messages(thread_uuid)
        history = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in messages
        ]
        system_instruction = thread["system_instruction"]
    else:
        # New thread - create it
        thread = await thread_service.create_thread(
            user_id=user_id,
            system_instruction=SYSTEM_INSTRUCTION,
            title=None,
        )
        if not thread:
            raise HTTPException(status_code=500, detail="Failed to create thread")
        thread_uuid = UUID(thread["id"])
        system_instruction = SYSTEM_INSTRUCTION

    # Process audio if provided
    audio_data = None
    audio_url = None
    if audio:
        audio_data = await audio.read()
        audio_url = await thread_service.upload_audio(
            user_id=user_id,
            thread_id=thread_uuid,
            audio_data=audio_data,
            filename=audio.filename or "audio.wav"
        )

    # Save user message
    user_message_content = message if message else "[Audio message]"
    await thread_service.add_message(
        thread_id=thread_uuid,
        role="user",
        content=user_message_content,
        audio_url=audio_url,
    )

    async def generate_stream():
        """Generate SSE stream of AI response"""
        # For new threads, send the thread_id first
        if is_new_thread:
            yield f"data: {json.dumps({'type': 'thread_created', 'thread_id': str(thread_uuid)})}\n\n"

        full_response = ""
        try:
            async for chunk in gemini_service.chat_stream(
                message=message,
                history=history,
                system_instruction=system_instruction,
                audio_data=audio_data,
            ):
                full_response += chunk
                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"

            # Save assistant response to database
            await thread_service.add_message(
                thread_id=thread_uuid,
                role="assistant",
                content=full_response,
            )

            # Generate title for new threads only
            if is_new_thread:
                try:
                    title = await gemini_service.generate_title(user_message_content, full_response)
                    await thread_service.update_thread(
                        thread_id=thread_uuid,
                        user_id=user_id,
                        title=title,
                    )
                    yield f"data: {json.dumps({'type': 'title_generated', 'title': title})}\n\n"
                except Exception:
                    pass  # Title generation is optional

            yield f"data: {json.dumps({'type': 'done', 'content': full_response})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/threads/{thread_id}/messages", response_model=list[MessageResponse])
async def get_messages(
    thread_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    thread_service: ThreadService = Depends(get_thread_service),
):
    """Get all messages in a thread"""
    # Verify thread belongs to user
    thread = await thread_service.get_thread(thread_id, user_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    return await thread_service.get_thread_messages(thread_id)
