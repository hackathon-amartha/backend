import os
import base64
from pathlib import Path
from typing import AsyncGenerator, List, Optional
from dotenv import load_dotenv
import google.generativeai as genai
from google.generativeai.types import ContentDict, PartDict

# Load .env from the backend directory
env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY must be set in environment variables")

genai.configure(api_key=GEMINI_API_KEY)


class GeminiService:
    MODEL_NAME = "gemini-2.5-flash"

    def __init__(self):
        self.model = genai.GenerativeModel(
            model_name=self.MODEL_NAME,
        )

    def _build_history(
        self,
        messages: List[dict],
        system_instruction: str
    ) -> List[ContentDict]:
        """Build chat history from messages for Gemini API"""
        history = []

        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            history.append({
                "role": role,
                "parts": [{"text": msg["content"]}]
            })

        return history

    async def chat_stream(
        self,
        message: str,
        history: List[dict],
        system_instruction: str,
        audio_data: Optional[bytes] = None,
        audio_mime_type: str = "audio/wav"
    ) -> AsyncGenerator[str, None]:
        """
        Stream chat response from Gemini.

        Args:
            message: The user's text message
            history: List of previous messages [{"role": "user"|"assistant", "content": "..."}]
            system_instruction: System instruction for the model
            audio_data: Optional audio file bytes
            audio_mime_type: MIME type of the audio file

        Yields:
            Chunks of the response text
        """
        # Create model with system instruction
        model = genai.GenerativeModel(
            model_name=self.MODEL_NAME,
            system_instruction=system_instruction
        )

        # Build conversation history
        chat_history = self._build_history(history, system_instruction)

        # Start chat with history
        chat = model.start_chat(history=chat_history)

        # Build the message parts
        parts: List[PartDict] = []

        # Add audio if provided
        if audio_data:
            audio_base64 = base64.b64encode(audio_data).decode("utf-8")
            parts.append({
                "inline_data": {
                    "mime_type": audio_mime_type,
                    "data": audio_base64
                }
            })
            # Add instruction to transcribe/process audio
            if message:
                parts.append({"text": message})
            else:
                parts.append({"text": "Please process this audio and respond appropriately."})
        else:
            parts.append({"text": message})

        # Send message and stream response
        response = await chat.send_message_async(parts, stream=True)

        async for chunk in response:
            if chunk.text:
                yield chunk.text

    async def chat(
        self,
        message: str,
        history: List[dict],
        system_instruction: str,
        audio_data: Optional[bytes] = None,
        audio_mime_type: str = "audio/wav"
    ) -> str:
        """
        Get complete chat response from Gemini (non-streaming).

        Args:
            message: The user's text message
            history: List of previous messages
            system_instruction: System instruction for the model
            audio_data: Optional audio file bytes
            audio_mime_type: MIME type of the audio file

        Returns:
            Complete response text
        """
        full_response = ""
        async for chunk in self.chat_stream(
            message=message,
            history=history,
            system_instruction=system_instruction,
            audio_data=audio_data,
            audio_mime_type=audio_mime_type
        ):
            full_response += chunk
        return full_response

    async def generate_title(self, user_message: str, assistant_response: str) -> str:
        """
        Generate a short title for the conversation thread.

        Args:
            user_message: The user's first message
            assistant_response: The assistant's response

        Returns:
            A short title (max 5 words)
        """
        from app.config import TITLE_GENERATION_PROMPT

        prompt = TITLE_GENERATION_PROMPT.format(
            message=user_message[:500],  # Limit message length
            response=assistant_response[:500]  # Limit response length
        )

        response = await self.model.generate_content_async(prompt)
        title = response.text.strip()

        # Ensure title is not too long
        words = title.split()
        if len(words) > 6:
            title = " ".join(words[:6])

        return title[:100]  # Max 100 characters


# Singleton instance
gemini_service = GeminiService()


def get_gemini_service() -> GeminiService:
    """Get Gemini service instance"""
    return gemini_service
