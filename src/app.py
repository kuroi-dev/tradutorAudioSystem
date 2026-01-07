import tkinter as tk
import threading
import queue
import pystray
from PIL import Image, ImageDraw

import sounddevice as sd
import numpy as np
import soundfile as sf
import whisper
import time
import os

# Configuración de audio
FS_CAPTURE = 44100
FS_MODEL = 16000
CHANNELS_CAPTURE = 2
DEVICE_ID = 20  # Mezcla estéreo (Realtek loopback)

# Cola para pasar fragmentos al hilo de transcripción
audio_queue = queue.Queue()
transcribing = False
stop_flag = threading.Event()

# Cargar modelo Whisper (elige 'small' o 'medium' para más precisión)
model = whisper.load_model("small")  # 'base' es más rápido, menos preciso

# UI básica
root = tk.Tk()
root.title("Transcriptor de audio del sistema")
root.geometry("700x250")

label_status = tk.Label(root, text="Estado: detenido", font=("Arial", 12))
label_status.pack(pady=5)

label_text = tk.Label(root, text="Transcripción aparecerá aquí", font=("Arial", 14), fg="black", wraplength=660, justify="left")
label_text.pack(pady=10)

def create_image():
    image = Image.new("RGB", (64, 64), "black")
    dc = ImageDraw.Draw(image)
    dc.rectangle((16, 16, 48, 48), fill="white")
    return image

def on_quit(icon, item):
    stop_flag.set()
    icon.stop()
    root.quit()

icon = pystray.Icon("Miapp", create_image(), menu=pystray.Menu(
    pystray.MenuItem("Salir", on_quit)
))

def run_icon():
    icon.run()

threading.Thread(target=run_icon, daemon=True).start()

# Función: normalizar a mono y 16 kHz
def to_mono_16k(audio_np, fs_in):
    # a) Stereo -> mono (promedio de canales)
    if audio_np.ndim == 2 and audio_np.shape[1] > 1:
        audio_mono = audio_np.mean(axis=1)
    else:
        audio_mono = audio_np.squeeze()
    # b) Resample simple a 16 kHz
    import math
    ratio = FS_MODEL / fs_in
    new_len = math.floor(len(audio_mono) * ratio)
    # Interpolación lineal (rápida). Para calidad top, usar resampy o torchaudio.
    x_old = np.linspace(0, 1, len(audio_mono), endpoint=False)
    x_new = np.linspace(0, 1, new_len, endpoint=False)
    audio_16k = np.interp(x_new, x_old, audio_mono).astype(np.float32)
    return audio_16k

# Hilo: captura por fragmentos
def capture_loop(chunk_seconds=5):
    global transcribing
    transcribing = True
    label_status.config(text="Estado: capturando y transcribiendo...")
    frames_per_chunk = int(FS_CAPTURE * chunk_seconds)
    while not stop_flag.is_set():
        try:
            audio_chunk = sd.rec(frames_per_chunk, samplerate=FS_CAPTURE,
                                 channels=CHANNELS_CAPTURE, dtype='float64',
                                 device=DEVICE_ID)
            sd.wait()
            audio_16k = to_mono_16k(audio_chunk, FS_CAPTURE)
            # Guarda a WAV temporal para Whisper
            ts = int(time.time() * 1000)
            tmp_path = f"chunk_{ts}.wav"
            sf.write(tmp_path, audio_16k, FS_MODEL, subtype='PCM_16')
            audio_queue.put(tmp_path)
        except Exception as e:
            root.after(0, lambda: label_status.config(text=f"Error de captura: {e}"))
            time.sleep(1)
    transcribing = False

# Hilo: transcripción Whisper
def transcribe_loop():
    buffer_text = ""
    while not stop_flag.is_set():
        try:
            tmp_path = audio_queue.get(timeout=0.5)
        except queue.Empty:
            continue
        try:
            result = model.transcribe(tmp_path, language="es", fp16=False)
            text = result.get("text", "").strip()
            if text:
                buffer_text += (" " + text) if buffer_text else text
                # Actualiza UI sin bloquear
                root.after(0, lambda t=buffer_text: label_text.config(text=t))
        except Exception as e:
            root.after(0, lambda: label_status.config(text=f"Error transcripción: {e}"))
        finally:
            # Limpia el archivo temporal
            try:
                os.remove(tmp_path)
            except:
                pass

# Botones
def start_transcription():
    if transcribing:
        return
    stop_flag.clear()
    threading.Thread(target=capture_loop, daemon=True).start()
    threading.Thread(target=transcribe_loop, daemon=True).start()
    label_status.config(text="Estado: iniciando...")

def stop_transcription():
    stop_flag.set()
    label_status.config(text="Estado: detenido")

btn_start = tk.Button(root, text="Iniciar transcripción (IA)", command=start_transcription)
btn_start.pack(pady=5)

btn_stop = tk.Button(root, text="Detener", command=stop_transcription)
btn_stop.pack(pady=5)

root.mainloop()
