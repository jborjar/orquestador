"""
Conversores - Audio y documentos
"""
import os
import base64
import subprocess
import tempfile
from io import BytesIO
from typing import List

import pdfplumber
import pytesseract
from PIL import Image
from pdf2image import convert_from_bytes

from config import OFFICE_EXTENSIONS, IMAGE_EXTENSIONS


def convert_audio_to_wav(audio_bytes: bytes, input_extension: str) -> bytes:
    """
    Convierte audio de cualquier formato a WAV usando ffmpeg.
    WAV 16kHz mono es el formato optimo para Whisper.
    """
    print(f"[DEBUG] Audio bytes: primeros 20 = {audio_bytes[:20]}")

    if input_extension == '.wav':
        return audio_bytes

    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = os.path.join(tmpdir, f"input{input_extension}")
        output_path = os.path.join(tmpdir, "output.wav")

        with open(input_path, "wb") as f:
            f.write(audio_bytes)

        written_size = os.path.getsize(input_path)
        print(f"[DEBUG] Archivo escrito: {input_path} ({written_size} bytes)")

        result = subprocess.run(
            ["ffmpeg", "-y", "-i", input_path, "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", output_path],
            capture_output=True,
            timeout=30
        )

        if result.returncode != 0:
            print(f"[DEBUG] FFmpeg error: {result.stderr.decode()}")
            raise Exception(f"Error convirtiendo audio: {result.stderr.decode()[:200]}")

        with open(output_path, "rb") as f:
            wav_bytes = f.read()

        print(f"[DEBUG] Audio convertido: {input_extension} -> .wav ({len(audio_bytes)} -> {len(wav_bytes)} bytes)")
        return wav_bytes


def convert_wav_to_ogg(wav_bytes: bytes) -> bytes:
    """
    Convierte audio WAV a OGG Opus usando ffmpeg.
    WhatsApp requiere OGG Opus para notas de voz.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = os.path.join(tmpdir, "input.wav")
        output_path = os.path.join(tmpdir, "output.ogg")

        with open(input_path, "wb") as f:
            f.write(wav_bytes)

        result = subprocess.run(
            ["ffmpeg", "-y", "-i", input_path, "-c:a", "libopus", "-b:a", "32k", output_path],
            capture_output=True,
            timeout=30
        )

        if result.returncode != 0:
            print(f"[DEBUG] FFmpeg WAV->OGG error: {result.stderr.decode()[:200]}")
            raise Exception(f"Error convirtiendo WAV a OGG: {result.stderr.decode()[:100]}")

        with open(output_path, "rb") as f:
            ogg_bytes = f.read()

        print(f"[DEBUG] Audio convertido: .wav -> .ogg ({len(wav_bytes)} -> {len(ogg_bytes)} bytes)")
        return ogg_bytes


def convert_office_to_pdf(file_bytes: bytes, extension: str) -> bytes:
    """Convierte archivo Office a PDF usando LibreOffice."""
    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = os.path.join(tmpdir, f"input{extension}")
        with open(input_path, "wb") as f:
            f.write(file_bytes)

        result = subprocess.run(
            ["libreoffice", "--headless", "--convert-to", "pdf", "--outdir", tmpdir, input_path],
            capture_output=True,
            timeout=60
        )

        if result.returncode != 0:
            raise Exception(f"Error al convertir a PDF: {result.stderr.decode()}")

        pdf_path = os.path.join(tmpdir, "input.pdf")
        if not os.path.exists(pdf_path):
            raise Exception("No se genero el PDF")

        with open(pdf_path, "rb") as f:
            return f.read()


def file_to_images_b64(file_bytes: bytes, filename: str) -> List[str]:
    """Convierte archivo (PDF, Office, imagen) a lista de imagenes base64."""
    ext = os.path.splitext(filename.lower())[1]
    images_b64 = []

    if ext in OFFICE_EXTENSIONS:
        file_bytes = convert_office_to_pdf(file_bytes, ext)
        ext = ".pdf"

    if ext == ".pdf":
        pages = convert_from_bytes(file_bytes)
        for page in pages:
            buf = BytesIO()
            page.save(buf, format="JPEG")
            images_b64.append(base64.b64encode(buf.getvalue()).decode("utf-8"))

    elif ext in IMAGE_EXTENSIONS:
        images_b64.append(base64.b64encode(file_bytes).decode("utf-8"))

    else:
        raise Exception(f"Formato no soportado: {ext}")

    return images_b64


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """
    Extrae texto de un PDF.
    Primero intenta extraer texto directamente (PDF con texto).
    Si no hay texto, usa OCR (PDF escaneado).
    """
    text_pages = []

    # Intentar extraer texto directamente con pdfplumber
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(pdf_bytes)
        pdf_path = f.name

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text() or ""
                if page_text.strip():
                    text_pages.append(f"--- Página {i+1} ---\n{page_text}")

        # Si obtuvimos texto, retornarlo
        if text_pages:
            full_text = "\n\n".join(text_pages)
            print(f"[DEBUG] PDF con texto extraído: {len(full_text)} caracteres")
            return full_text
    finally:
        os.unlink(pdf_path)

    # Si no hay texto, usar OCR
    print("[DEBUG] PDF sin texto, usando OCR...")
    images = convert_from_bytes(pdf_bytes)

    for i, img in enumerate(images):
        page_text = pytesseract.image_to_string(img, lang="spa")
        if page_text.strip():
            text_pages.append(f"--- Página {i+1} ---\n{page_text}")

    full_text = "\n\n".join(text_pages) if text_pages else "No se pudo extraer texto del documento."
    print(f"[DEBUG] OCR completado: {len(full_text)} caracteres")
    return full_text


def extract_text_from_file(file_bytes: bytes, filename: str) -> str:
    """
    Extrae texto de un archivo (PDF, Office, imagen).
    """
    ext = os.path.splitext(filename.lower())[1]

    # Convertir Office a PDF primero
    if ext in OFFICE_EXTENSIONS:
        file_bytes = convert_office_to_pdf(file_bytes, ext)
        ext = ".pdf"

    if ext == ".pdf":
        return extract_text_from_pdf(file_bytes)

    elif ext in IMAGE_EXTENSIONS:
        # OCR directo para imágenes
        img = Image.open(BytesIO(file_bytes))
        text = pytesseract.image_to_string(img, lang="spa")
        print(f"[DEBUG] OCR imagen: {len(text)} caracteres")
        return text if text.strip() else "No se pudo extraer texto de la imagen."

    else:
        raise Exception(f"Formato no soportado: {ext}")
