# app/routers/stt.py
import os
import tempfile
import logging
import json
import traceback
from typing import Optional, Dict, Any, AsyncGenerator
from uuid import UUID

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Header, Form
from fastapi.responses import JSONResponse, StreamingResponse
from supabase import Client
import httpx
from dotenv import load_dotenv

from app.database import get_supabase
from app.services.thread import get_thread_service, ThreadService

# Load env from project root (where main.py/.env located)
load_dotenv()

router = APIRouter(prefix="/stt", tags=["speech-to-text"])

# Configuration from .env
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_STT_URL = os.getenv(
    "GROQ_STT_URL",
    "https://api.groq.com/openai/v1/audio/transcriptions"
)
GROQ_API_BASE = os.getenv("GROQ_API_BASE", "https://api.groq.com/openai/v1")
GROQ_STT_MODEL = os.getenv("GROQ_STT_MODEL", "whisper-large-v3")
GROQ_LLM_MODEL = os.getenv("GROQ_LLM_MODEL", "meta-llama/llama-4-maverick-17b-128e-instruct")  # change as needed

logger = logging.getLogger("uvicorn.error")

if not GROQ_API_KEY:
    logger.warning("GROQ_API_KEY not set — STT/LLM calls will fail until configured.")


# -------------------- Auth Helper --------------------

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


# -------------------- Helpers --------------------

async def save_upload_to_tempfile(upload_file: UploadFile) -> str:
    """
    Save incoming UploadFile to a temporary file on disk and return path.
    Streamed read to avoid large memory usage.
    """
    suffix = ""
    if upload_file.filename and "." in upload_file.filename:
        suffix = "." + upload_file.filename.rsplit(".", 1)[1]
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    with open(tmp_path, "wb") as f:
        while True:
            chunk = await upload_file.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
    await upload_file.close()
    return tmp_path


def extract_text_from_llm_response(resp_json: Dict[str, Any]) -> str:
    """
    Try to extract the text reply from common response shapes.
    Falls back to stringify the JSON if needed.
    """
    if not isinstance(resp_json, dict):
        return str(resp_json)

    # OpenAI-style choices -> chat/completions
    choices = resp_json.get("choices")
    if isinstance(choices, list) and len(choices) > 0:
        first = choices[0]
        # chat message object
        msg = first.get("message") or first.get("message", {})
        if isinstance(msg, dict):
            content = msg.get("content")
            if isinstance(content, list) and len(content) > 0:
                piece = content[0]
                if isinstance(piece, dict) and "text" in piece:
                    return piece["text"]
                return str(piece)
            if isinstance(content, str):
                return content
        # older completion style
        if "text" in first and isinstance(first["text"], str):
            return first["text"]

    # responses-style convenience fields
    if "output_text" in resp_json and isinstance(resp_json["output_text"], str):
        return resp_json["output_text"]

    if "text" in resp_json and isinstance(resp_json["text"], str):
        return resp_json["text"]

    # fallback: stringify
    try:
        return json.dumps(resp_json)
    except Exception:
        return str(resp_json)


# -------------------- System context --------------------

SYSTEM_CONTEXT = """
Anda adalah Asisten Customer Service Amartha yang ramah dan membantu.

## TENTANG AMARTHA
Amartha adalah perusahaan fintech P2P Lending yang terdaftar dan diawasi OJK, fokus memberdayakan UMKM perempuan di Indonesia melalui model Grameen Bank. Amartha berdiri sejak tahun 2010 dan dipimpin oleh CEO Andi Taufan Garuda Putra.

**AmarthaFin:**
AmarthaFin adalah aplikasi Amartha yang menyimpan dan mengelola semua produk digital Amartha, termasuk Modal (pinjaman), Celengan (investasi), dan AmarthaLink (layanan PPOB).

**Lokasi Poin Amartha:**
Poin layanan Amartha tersebar di Jawa, Sumatera, Sulawesi, Bali, Nusa Tenggara, dan Kalimantan. Untuk mencari poin terdekat dari lokasi Anda, silakan hubungi WhatsApp: 0811-1915-0170.

## PRODUK & LAYANAN

### 1. MODAL (Pinjaman untuk Mitra Perempuan UMKM)
Modal adalah produk pinjaman Amartha yang dirancang khusus untuk memberdayakan perempuan pengusaha mikro.

**Persyaratan:**
- Khusus untuk perempuan mitra UMKM usia 18-58 tahun
- Sistem majelis: kelompok 5 orang, bergabung ke majelis 15-20 orang
- Tanggung renteng: anggota saling menjamin kredibilitas
- Harus memiliki usaha mikro dan aktif dalam kelompok

**Detail Produk:**
- Jumlah pinjaman: hingga Rp30 juta
- Pembayaran (repayment): via AmarthaFin
- Bisa pinjam lagi setelah lunas, jumlahnya bisa lebih besar kalau riwayat pembayaran Anda lancar
- Setiap pengajuan akan dievaluasi berdasarkan kemampuan bayar Anda

**Cara Mengajukan Modal:**
1. Buka aplikasi/website Amartha
2. Klik menu "Modal" di homepage
3. Hubungi nomor Business Partner (BP) yang tertera di layar
4. BP akan membantu proses pengajuan hingga pencairan

### 2. CELENGAN (Investasi untuk Pendana)
Platform investasi mulai dari Rp10.000, semua jangka waktu 12 bulan, bisa ditarik setelah 1 bulan, keuntungan diterima tiap bulan, tanpa biaya admin:

- **Celengan Pengrajin Lokal**: 6,5%/tahun, min Rp12,5 juta
- **Celengan Lebaran**: 5%/tahun, min Rp10.000
- **Celengan Liburan Akhir Tahun**: 6,5%/tahun, min Rp10 juta
- **Celengan Pertanian Nusantara**: 6,5%/tahun, min Rp15 juta
- **Celengan Peternakan Daging Lokal**: 6%/tahun, min Rp5 juta
- **Celengan Pasar Rakyat**: 5,5%/tahun, min Rp500.000
- **Celengan Warung Usaha Mikro**: 7%/tahun, min Rp50 juta (atau 8%/tahun, min Rp100 juta)
- **Celengan Pendidikan Anak**: 5%/tahun, min Rp10.000

**Cara Berinvestasi di Celengan:**
1. Buka aplikasi/website Amartha dan klik menu "Celengan"
2. Lakukan verifikasi data diri Anda
3. Pilih tipe celengan yang sesuai dengan tujuan investasi Anda
4. Masukkan nominal yang ingin diinvestasikan (pastikan saldo Pocket Amartha mencukupi)
5. Masukkan PIN untuk konfirmasi
6. Selesai! Investasi Anda aktif dan keuntungan akan diterima setiap bulan

### 3. AMARTHALINK (Layanan PPOB)
**Fitur layanan**: Pulsa, paket data, listrik, PDAM, internet & TV kabel, zakat & sedekah, tarik tunai
**Keuntungan jadi mitra AmarthaLink**:
- Komisi dari setiap transaksi sukses
- Komisi dari referral yang layak
- Tidak butuh modal besar
- Membantu pemberdayaan ekonomi lokal

**Cara Isi Paket Data (untuk mitra AmarthaLink):**
1. Klik menu "Paket Data" di AmarthaLink
2. Masukkan nomor HP pelanggan
3. Pilih paket data yang tersedia
4. Masukkan harga untuk pelanggan
5. Lakukan pembayaran
6. Selesai! Paket data akan terkirim ke nomor pelanggan

**Cara Tarik Tunai (untuk mitra AmarthaLink):**
1. Klik menu "Tarik Tunai" di AmarthaLink
2. Masukkan nominal tarik tunai yang diminta pelanggan
3. Klik "Lanjutkan"
4. Minta pelanggan scan QR code melalui aplikasi Amartha mereka
5. Setelah pembayaran berhasil, berikan uang tunai kepada pelanggan
6. Transaksi selesai! Anda akan mendapatkan komisi dari layanan ini

## CARA TOP UP POCKET AMARTHA
1. Klik "Isi Saldo" di homepage
2. Pilih "Pocket"
3. Pilih metode pengisian (transfer bank, virtual account, dll)
4. Ikuti cara pembayaran sesuai metode yang dipilih
5. Saldo akan masuk ke Pocket Amartha setelah pembayaran berhasil

## CARA MENJAWAB
- Gunakan bahasa Indonesia yang ramah, sopan, dan hangat
- Gunakan sapaan "Anda" (bukan "Ibu" atau "Bapak")
- Jawaban HARUS sesimpel dan seringkas mungkin (maksimal 2-3 kalimat atau poin-poin pendek)
- SELALU gunakan format poin-poin (bullet points) untuk penjelasan yang lebih dari 1 langkah
- Gunakan bahasa sehari-hari yang mudah dipahami ibu-ibu, HINDARI istilah teknis dan formal
- JANGAN mengulang nama produk di setiap kalimat (contoh: BURUK: "Modal adalah pinjaman Modal untuk...", BAIK: "Modal adalah pinjaman untuk...")
- HANYA jawab topik seputar Amartha dan layanan yang tersedia di amartha.com
- Boleh jawab study case/issue mitra dan solusinya
- JANGAN bahas topik sensitif (politik, SARA, atau di luar scope bisnis Amartha)

## JIKA TIDAK TAHU / DI LUAR TOPIK
"Maaf, saya tidak dapat menjawab pertanyaan tersebut. Ada yang bisa saya bantu terkait layanan Amartha?"

## JIKA USER KOMPLAIN / BUTUH ESCALATION
"Mohon maaf atas kendala yang Anda alami. Untuk penanganan lebih lanjut, silakan hubungi:

📞 Layanan Pengaduan Konsumen: 150170
💬 WhatsApp: 0811-1915-0170
📧 Email: support@amartha.com

Atau hubungi Direktorat Jenderal Perlindungan Konsumen dan Tertib Niaga Kementerian Perdagangan RI:
💬 WhatsApp: 0853-1111-1010"

Goal: Bantu user dengan informasi akurat, ramah, dan solutif berdasarkan transcript yang diterima.
"""


# -------------------- Endpoint --------------------

@router.post("/groq_simple")
async def groq_stt_and_llm(
    audio: UploadFile = File(...),
    stt_model: Optional[str] = None,
    llm_model: Optional[str] = None
) -> Dict[str, Any]:
    """
    Minimal flow using Groq only:
      - receive audio via multipart 'audio'
      - transcribe via Groq STT
      - send transcript to Groq LLM (chat/completions)
      - return JSON: { transcript, llm_raw, llm_text }
    """
    if not GROQ_API_KEY:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY not configured in environment")

    # validate content type
    ct = audio.content_type or ""
    if not (ct.startswith("audio/") or ct.startswith("video/")):
        raise HTTPException(status_code=400, detail="Upload an audio/video file (Content-Type audio/* or video/*)")

    # save uploaded file to disk (streamed)
    tmp_path = await save_upload_to_tempfile(audio)

    # ---------- 1) Groq STT ----------
    transcript = ""
    stt_json = {}
    try:
        with open(tmp_path, "rb") as fh:
            files = {"file": (os.path.basename(tmp_path), fh, ct)}
            data = {"model": stt_model or GROQ_STT_MODEL}
            headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}

            async with httpx.AsyncClient(timeout=180.0) as client:
                try:
                    stt_resp = await client.post(GROQ_STT_URL, headers=headers, data=data, files=files)
                except httpx.RequestError as req_err:
                    # network / connection error
                    logger.exception("Network error calling Groq STT: %s", repr(req_err))
                    # do not expose internal traceback to client; use repr for concise message
                    raise HTTPException(status_code=502, detail=f"Groq STT network error: {repr(req_err)}")

        # status code check (response exists here)
        if stt_resp.status_code >= 400:
            logger.error("Groq STT error %s: %s", stt_resp.status_code, stt_resp.text)
            return JSONResponse(status_code=502, content={"error": "Groq STT error", "body": stt_resp.text})

        # try parse JSON separately so we can catch decode errors
        try:
            stt_json = stt_resp.json()
        except ValueError as json_err:
            logger.exception("Failed to parse JSON from Groq STT")
            raise HTTPException(
                status_code=502,
                detail=f"Groq STT returned invalid JSON: {repr(json_err)}. Raw (truncated): {stt_resp.text[:1000]!r}"
            )

        transcript = stt_json.get("text") or stt_json.get("transcript") or ""
    except HTTPException:
        # re-raise HTTPExceptions unchanged
        raise
    except Exception as e:
        tb = traceback.format_exc()
        logger.error("Groq STT request failed: %s\n%s", repr(e), tb)
        raise HTTPException(status_code=502, detail=f"Groq STT request failed: {repr(e)}")
    finally:
        # cleanup tmp file (always attempt)
        try:
            os.remove(tmp_path)
        except Exception:
            logger.debug("Failed to remove tmp file %s", tmp_path)

    # ---------- 2) Groq LLM ----------
    llm_endpoint = f"{GROQ_API_BASE.rstrip('/')}/chat/completions"
    model_to_use = llm_model or GROQ_LLM_MODEL
    user_prompt = f"Transcript:\n{transcript}\n\nPlease reply concisely according to the system rules."

    llm_body = {
        "model": model_to_use,
        "messages": [
            {"role": "system", "content": SYSTEM_CONTEXT},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.0,
        "max_tokens": 300
    }

    llm_json: Dict[str, Any] = {}
    llm_text = ""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
            try:
                llm_resp = await client.post(llm_endpoint, headers=headers, json=llm_body)
            except httpx.RequestError as req_err:
                logger.exception("Network error calling Groq LLM: %s", repr(req_err))
                raise JSONResponse(status_code=502, content={"error": "Groq LLM network error", "detail": repr(req_err)})

        if llm_resp.status_code >= 400:
            logger.error("Groq LLM error %s: %s", llm_resp.status_code, llm_resp.text)
            return JSONResponse(status_code=502, content={"error": "Groq LLM error", "body": llm_resp.text})

        try:
            llm_json = llm_resp.json()
        except ValueError as json_err:
            logger.exception("Failed to parse JSON from Groq LLM")
            return JSONResponse(status_code=502, content={
                "error": "Groq LLM returned invalid JSON",
                "detail": repr(json_err),
                "raw_truncated": llm_resp.text[:1000]
            })

        llm_text = extract_text_from_llm_response(llm_json)
    except JSONResponse:
        # returned already-formed JSONResponse
        raise
    except Exception as e:
        tb = traceback.format_exc()
        logger.error("Groq LLM request failed: %s\n%s", repr(e), tb)
        return JSONResponse(status_code=502, content={"error": f"Groq LLM request failed: {repr(e)}"})

    # ---------- return ----------
    return {
        "transcript": transcript,
        "llm_raw": llm_json,
        "llm_text": llm_text
    }


@router.post("/groq_stream")
async def groq_stt_and_llm_stream(
    audio: UploadFile = File(...),
    thread_id: Optional[str] = Form(None),
    stt_model: Optional[str] = Form(None),
    llm_model: Optional[str] = Form(None),
    user_id: UUID = Depends(get_current_user_id),
    thread_service: ThreadService = Depends(get_thread_service),
):
    """
    STT + LLM with streaming response via Server-Sent Events (SSE).

    Supports thread continuation like Gemini chat endpoint:
    - If thread_id provided: continues existing conversation with audio input
    - If thread_id not provided: creates new thread

    Flow:
      1. Create/get thread
      2. Transcribe audio via Groq STT
      3. Save user message (with audio URL)
      4. Stream LLM response via SSE (with conversation history)
      5. Save assistant response

    SSE Events:
      - type: 'thread_created' - New thread ID (if new thread)
      - type: 'transcript' - Transcribed text
      - type: 'chunk' - Streaming chunks of LLM response
      - type: 'done' - Final complete response
      - type: 'title_generated' - Auto-generated title (if new thread)
      - type: 'error' - Error occurred
    """
    if not GROQ_API_KEY:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY not configured in environment")

    # validate content type
    ct = audio.content_type or ""
    if not (ct.startswith("audio/") or ct.startswith("video/")):
        raise HTTPException(status_code=400, detail="Upload an audio/video file (Content-Type audio/* or video/*)")

    # -------------------- Thread Management --------------------
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
            system_instruction=SYSTEM_CONTEXT,
            title=None,
        )
        if not thread:
            raise HTTPException(status_code=500, detail="Failed to create thread")
        thread_uuid = UUID(thread["id"])
        system_instruction = SYSTEM_CONTEXT

    # save uploaded file to disk (streamed)
    tmp_path = await save_upload_to_tempfile(audio)

    # ---------- 1) Groq STT ----------
    transcript = ""
    try:
        with open(tmp_path, "rb") as fh:
            files = {"file": (os.path.basename(tmp_path), fh, ct)}
            data = {"model": stt_model or GROQ_STT_MODEL}
            headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}

            async with httpx.AsyncClient(timeout=180.0) as client:
                try:
                    stt_resp = await client.post(GROQ_STT_URL, headers=headers, data=data, files=files)
                except httpx.RequestError as req_err:
                    logger.exception("Network error calling Groq STT: %s", repr(req_err))
                    raise HTTPException(status_code=502, detail=f"Groq STT network error: {repr(req_err)}")

        if stt_resp.status_code >= 400:
            logger.error("Groq STT error %s: %s", stt_resp.status_code, stt_resp.text)
            raise HTTPException(status_code=502, detail=f"Groq STT error: {stt_resp.text}")

        try:
            stt_json = stt_resp.json()
        except ValueError as json_err:
            logger.exception("Failed to parse JSON from Groq STT")
            raise HTTPException(
                status_code=502,
                detail=f"Groq STT returned invalid JSON: {repr(json_err)}"
            )

        transcript = stt_json.get("text") or stt_json.get("transcript") or ""
    except HTTPException:
        raise
    except Exception as e:
        tb = traceback.format_exc()
        logger.error("Groq STT request failed: %s\n%s", repr(e), tb)
        raise HTTPException(status_code=502, detail=f"Groq STT request failed: {repr(e)}")
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            logger.debug("Failed to remove tmp file %s", tmp_path)

    # -------------------- Save Audio & User Message --------------------
    # Upload audio to storage
    audio_data = open(tmp_path, "rb").read() if os.path.exists(tmp_path) else None
    audio_url = None
    if audio_data:
        audio_url = await thread_service.upload_audio(
            user_id=user_id,
            thread_id=thread_uuid,
            audio_data=audio_data,
            filename="audio.wav"
        )

    # Save user message
    await thread_service.add_message(
        thread_id=thread_uuid,
        role="user",
        content=transcript or "[Audio message]",
        audio_url=audio_url,
    )

    # ---------- 2) Stream LLM Response ----------
    async def generate_stream() -> AsyncGenerator[str, None]:
        """Generate SSE stream of LLM response"""
        # For new threads, send the thread_id first
        if is_new_thread:
            yield f"data: {json.dumps({'type': 'thread_created', 'thread_id': str(thread_uuid)})}\n\n"

        # Send transcript
        yield f"data: {json.dumps({'type': 'transcript', 'content': transcript})}\n\n"

        llm_endpoint = f"{GROQ_API_BASE.rstrip('/')}/chat/completions"
        model_to_use = llm_model or GROQ_LLM_MODEL

        # Build messages with history
        messages = [{"role": "system", "content": system_instruction}]
        messages.extend(history)
        messages.append({"role": "user", "content": transcript})

        llm_body = {
            "model": model_to_use,
            "messages": messages,
            "temperature": 0.0,
            "max_tokens": 300,
            "stream": True  # Enable streaming
        }

        full_response = ""
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
                async with client.stream("POST", llm_endpoint, headers=headers, json=llm_body) as llm_resp:
                    if llm_resp.status_code >= 400:
                        error_text = await llm_resp.aread()
                        logger.error("Groq LLM error %s: %s", llm_resp.status_code, error_text.decode())
                        yield f"data: {json.dumps({'type': 'error', 'content': 'Groq LLM error'})}\n\n"
                        return

                    # Stream chunks
                    async for line in llm_resp.aiter_lines():
                        if not line or line.startswith(":"):
                            continue

                        if line.startswith("data: "):
                            line = line[6:]  # Remove "data: " prefix

                        if line == "[DONE]":
                            break

                        try:
                            chunk_json = json.loads(line)
                            choices = chunk_json.get("choices", [])
                            if choices and len(choices) > 0:
                                delta = choices[0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    full_response += content
                                    yield f"data: {json.dumps({'type': 'chunk', 'content': content})}\n\n"
                        except json.JSONDecodeError:
                            continue

            # Save assistant response to database
            await thread_service.add_message(
                thread_id=thread_uuid,
                role="assistant",
                content=full_response,
            )

            # Generate title for new threads only
            if is_new_thread:
                try:
                    from app.services.gemini import get_gemini_service
                    gemini = get_gemini_service()
                    title = await gemini.generate_title(transcript, full_response)
                    await thread_service.update_thread(
                        thread_id=thread_uuid,
                        user_id=user_id,
                        title=title,
                    )
                    yield f"data: {json.dumps({'type': 'title_generated', 'title': title})}\n\n"
                except Exception:
                    pass  # Title generation is optional

            # Send done event
            yield f"data: {json.dumps({'type': 'done', 'content': full_response})}\n\n"

        except Exception as e:
            tb = traceback.format_exc()
            logger.error("Groq LLM stream failed: %s\n%s", repr(e), tb)
            yield f"data: {json.dumps({'type': 'error', 'content': f'LLM error: {repr(e)}'})}\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
