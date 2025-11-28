from typing import List, Optional
from uuid import UUID
from datetime import datetime
from supabase import Client
from app.database import get_supabase


class ThreadService:
    def __init__(self):
        self.supabase: Client = get_supabase()

    async def create_thread(
        self,
        user_id: UUID,
        system_instruction: str,
        title: Optional[str] = None
    ) -> dict:
        """Create a new chat thread"""
        data = {
            "user_id": str(user_id),
            "system_instruction": system_instruction,
            "title": title,
        }

        result = self.supabase.table("threads").insert(data).execute()
        return result.data[0] if result.data else None

    async def get_thread(self, thread_id: UUID, user_id: UUID) -> Optional[dict]:
        """Get a thread by ID (with user verification)"""
        result = (
            self.supabase.table("threads")
            .select("*")
            .eq("id", str(thread_id))
            .eq("user_id", str(user_id))
            .single()
            .execute()
        )
        return result.data if result.data else None

    async def get_user_threads(self, user_id: UUID) -> List[dict]:
        """Get all threads for a user"""
        result = (
            self.supabase.table("threads")
            .select("*")
            .eq("user_id", str(user_id))
            .order("updated_at", desc=True)
            .execute()
        )
        return result.data or []

    async def update_thread(
        self,
        thread_id: UUID,
        user_id: UUID,
        title: Optional[str] = None,
        system_instruction: Optional[str] = None
    ) -> Optional[dict]:
        """Update a thread"""
        data = {"updated_at": datetime.utcnow().isoformat()}
        if title is not None:
            data["title"] = title
        if system_instruction is not None:
            data["system_instruction"] = system_instruction

        result = (
            self.supabase.table("threads")
            .update(data)
            .eq("id", str(thread_id))
            .eq("user_id", str(user_id))
            .execute()
        )
        return result.data[0] if result.data else None

    async def delete_thread(self, thread_id: UUID, user_id: UUID) -> bool:
        """Delete a thread and all its messages"""
        result = (
            self.supabase.table("threads")
            .delete()
            .eq("id", str(thread_id))
            .eq("user_id", str(user_id))
            .execute()
        )
        return len(result.data) > 0 if result.data else False

    async def add_message(
        self,
        thread_id: UUID,
        role: str,
        content: str,
        audio_url: Optional[str] = None
    ) -> dict:
        """Add a message to a thread"""
        data = {
            "thread_id": str(thread_id),
            "role": role,
            "content": content,
            "audio_url": audio_url,
        }

        result = self.supabase.table("messages").insert(data).execute()

        # Update thread's updated_at timestamp
        self.supabase.table("threads").update(
            {"updated_at": datetime.utcnow().isoformat()}
        ).eq("id", str(thread_id)).execute()

        return result.data[0] if result.data else None

    async def get_thread_messages(self, thread_id: UUID) -> List[dict]:
        """Get all messages in a thread ordered by creation time"""
        result = (
            self.supabase.table("messages")
            .select("*")
            .eq("thread_id", str(thread_id))
            .order("created_at", desc=False)
            .execute()
        )
        return result.data or []

    async def upload_audio(
        self,
        user_id: UUID,
        thread_id: UUID,
        audio_data: bytes,
        filename: str
    ) -> str:
        """Upload audio file to Supabase storage and return URL"""
        path = f"{user_id}/{thread_id}/{filename}"

        # Upload to storage bucket
        self.supabase.storage.from_("audio").upload(
            path=path,
            file=audio_data,
            file_options={"content-type": "audio/wav"}
        )

        # Get public URL
        url = self.supabase.storage.from_("audio").get_public_url(path)
        return url


# Singleton instance
thread_service = ThreadService()


def get_thread_service() -> ThreadService:
    """Get thread service instance"""
    return thread_service
