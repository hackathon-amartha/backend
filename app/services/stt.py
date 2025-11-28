# app/routers/stt.py
import os
import tempfile
import logging
import json
import traceback
from typing import Optional, Dict, Any, AsyncGenerator

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
import httpx
from dotenv import load_dotenv

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
Amartha adalah perusahaan fintech P2P Lending yang terdaftar dan diawasi OJK, fokus memberdayakan UMKM perempuan di Indonesia melalui model Grameen Bank.

## PRODUK & LAYANAN

### 1. PINJAMAN UNTUK MITRA (Perempuan UMKM)
**Group Loan & Modal** (sama, bedanya cara repayment)
- Khusus untuk perempuan mitra UMKM usia 18-58 tahun
- Sistem majelis: kelompok 5 orang, bergabung ke majelis 15-20 orang
- Tanggung renteng: anggota saling menjamin kredibilitas
- Harus memiliki usaha mikro dan aktif dalam kelompok
- Jumlah pinjaman: hingga Rp30 juta
- Group Loan: repayment cash | Modal: repayment via AmarthaFin

**Cara Mengajukan Pinjaman Modal:**
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

### 3. AMARTHALINK (Agen PPOB)
**Fitur layanan**: Pulsa, paket data, listrik, PDAM, internet & TV kabel, zakat & sedekah
**Keuntungan jadi agen**:
- Komisi dari setiap transaksi sukses
- Komisi dari referral peminjam yang layak
- Tidak butuh modal besar
- Membantu pemberdayaan ekonomi lokal

## CARA MENJAWAB
- Gunakan bahasa Indonesia yang ramah, sopan, dan hangat
- Gunakan sapaan "Anda" (bukan "Ibu" atau "Bapak")
- Jawaban singkat dan jelas (1-3 kalimat), hindari jargon teknis
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
    stt_model: Optional[str] = None,
    llm_model: Optional[str] = None
):
    """
    STT + LLM with streaming response via Server-Sent Events (SSE).

    Flow:
      1. Transcribe audio via Groq STT
      2. Stream LLM response via SSE

    SSE Events:
      - type: 'transcript' - Contains the transcribed text
      - type: 'chunk' - Streaming chunks of LLM response
      - type: 'done' - Final complete response
      - type: 'error' - Error occurred
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

    # ---------- 2) Stream LLM Response ----------
    async def generate_stream() -> AsyncGenerator[str, None]:
        """Generate SSE stream of LLM response"""
        # Send transcript first
        yield f"data: {json.dumps({'type': 'transcript', 'content': transcript})}\n\n"

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
