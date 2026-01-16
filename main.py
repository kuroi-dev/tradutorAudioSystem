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
from deep_translator import GoogleTranslator

# Configuración del sistema híbrido dual
FS_CAPTURE = 44100
FS_MODEL = 16000
CHANNELS_CAPTURE = 2
DEVICE_ID = 0  # Microsoft Sound Mapper
CHUNK_SIZE = 2048  

# Configuración tiempo real
REALTIME_WINDOW_SECONDS = 3  # Ventana pequeña para tiempo real
SILENCE_THRESHOLD = 0.0005   # Umbral para detectar silencio
SILENCE_DURATION = 0.1       # 0.1 segundos de silencio para procesar

# Configuración contextual (cada 15 minutos)
CONTEXT_INTERVAL_MINUTES = 15  # Procesar contexto cada 15 minutos
CONTEXT_OVERLAP_SECONDS = 30   # Overlap de 30 segundos entre contextos

# Sistema híbrido dual
audio_stream = queue.Queue(maxsize=50)  # Stream continuo
realtime_queue = queue.Queue(maxsize=10)  # Cola para tiempo real
context_queue = queue.Queue(maxsize=5)    # Cola para contexto periódico
transcribing = False
stop_flag = threading.Event()

# Buffers duales
realtime_buffer = np.array([], dtype=np.float64)  # Buffer para tiempo real
context_buffer = np.array([], dtype=np.float64)   # Buffer para contexto (15 min)
buffer_lock = threading.Lock()

# Control de tiempo
last_realtime_process = 0
last_context_process = 0
context_start_time = 0

# Detector de pausas
silence_start_time = 0
is_in_silence = False

# Cargar modelo Whisper y traductor
model = whisper.load_model("small")  # Modelo para transcripción
translator = GoogleTranslator(source='en', target='es')  # Google Translate para traducción

# UI mejorada
root = tk.Tk()
root.title("Traductor de Audio en Tiempo Real - EN → ES")
root.geometry("800x400")
root.configure(bg="#2c3e50")

# Estilo de la UI
title_label = tk.Label(root, text="🧠 Traductor Contextual de Conversaciones - EN → ES", 
                      font=("Arial", 16, "bold"), fg="#ecf0f1", bg="#2c3e50")
title_label.pack(pady=10)

status_frame = tk.Frame(root, bg="#2c3e50")
status_frame.pack(pady=5)

label_status = tk.Label(status_frame, text="Estado: Detenido", font=("Arial", 12), 
                       fg="#e74c3c", bg="#2c3e50")
label_status.pack()

# Frame para el texto original (inglés)
original_frame = tk.Frame(root, bg="#34495e", relief="ridge", bd=2)
original_frame.pack(pady=5, padx=20, fill="both", expand=True)

original_title = tk.Label(original_frame, text="🇺🇸 Audio Original (Inglés):", 
                         font=("Arial", 12, "bold"), fg="#3498db", bg="#34495e")
original_title.pack(anchor="w", padx=10, pady=5)

label_original = tk.Label(original_frame, text="El audio transcrito aparecerá aquí...", 
                         font=("Arial", 11), fg="#ecf0f1", bg="#34495e", 
                         wraplength=750, justify="left", anchor="nw")
label_original.pack(padx=10, pady=5, fill="both", expand=True)

# Frame para la traducción (español)
translation_frame = tk.Frame(root, bg="#27ae60", relief="ridge", bd=2)
translation_frame.pack(pady=5, padx=20, fill="both", expand=True)

translation_title = tk.Label(translation_frame, text="🇪🇸 Traducción (Español):", 
                            font=("Arial", 12, "bold"), fg="#ffffff", bg="#27ae60")
translation_title.pack(anchor="w", padx=10, pady=5)

label_translation = tk.Label(translation_frame, text="La traducción aparecerá aquí...", 
                            font=("Arial", 11), fg="#ffffff", bg="#27ae60", 
                            wraplength=750, justify="left", anchor="nw")
label_translation.pack(padx=10, pady=5, fill="both", expand=True)

def create_image():
    """Crear icono para la bandeja del sistema"""
    image = Image.new("RGB", (64, 64), "#2c3e50")
    dc = ImageDraw.Draw(image)
    dc.rectangle((16, 16, 48, 48), fill="#3498db")
    dc.text((20, 25), "TR", fill="white")
    return image

def on_quit(icon, item):
    stop_flag.set()
    icon.stop()
    root.quit()

# Icono en bandeja del sistema
icon = pystray.Icon("Traductor", create_image(), menu=pystray.Menu(
    pystray.MenuItem("Salir", on_quit)
))

def run_icon():
    icon.run()

threading.Thread(target=run_icon, daemon=True).start()

# Función: diagnosticar dispositivos de audio
def get_best_audio_device():
    """Encontrar el mejor dispositivo para capturar audio del sistema"""
    devices = sd.query_devices()
    
    # Prioridades de dispositivos (en orden)
    priorities = [
        "Microsoft Sound Mapper",  # Captura TODO el audio del sistema
        "Primary Sound Capture",  # Alternativa
        "Mezcla estéreo",         # Para audio Realtek
        "Stereo Mix"              # Inglés
    ]
    
    for priority in priorities:
        for i, device in enumerate(devices):
            if (device['max_input_channels'] > 0 and 
                priority.lower() in device['name'].lower()):
                print(f"✅ Dispositivo seleccionado: ID {i} - {device['name']}")
                return i
    
    # Si no encuentra ninguno, usar el primero con entrada
    for i, device in enumerate(devices):
        if device['max_input_channels'] > 0:
            print(f"⚠️ Usando dispositivo por defecto: ID {i} - {device['name']}")
            return i
    
    raise Exception("No se encontró ningún dispositivo de entrada de audio")

def diagnose_audio():
    """Mostrar dispositivos de audio disponibles para debugging"""
    try:
        devices = sd.query_devices()
        print("=== DISPOSITIVOS DE AUDIO DISPONIBLES ===")
        for i, device in enumerate(devices):
            if device['max_input_channels'] > 0:
                marker = ""
                if "Microsoft Sound Mapper" in device['name']:
                    marker = " 🎯 (IDEAL para Bluetooth)"
                elif "Primary Sound" in device['name']:
                    marker = " 🔄 (Alternativa)"
                elif "Mezcla" in device['name'] or "Stereo" in device['name']:
                    marker = " 🎵 (Solo para Realtek)"
                
                print(f"ID {i}: {device['name']} (entrada: {device['max_input_channels']} canales){marker}")
        print("=" * 50)
        
        # Recomendar dispositivo
        best_device = get_best_audio_device()
        return best_device
        
    except Exception as e:
        print(f"Error al consultar dispositivos: {e}")
        return 0

# Hilo: captura de audio en tiempo real (streaming continuo)
def audio_stream_callback(indata, frames, time, status):
    """Callback para captura continua de audio"""
    if status:
        print(f"Audio status: {status}")
    
    # Manejar tanto mono como estéreo
    if len(indata.shape) == 2 and indata.shape[1] > 1:
        # Estéreo -> mono
        mono_data = indata.mean(axis=1)
    else:
        # Ya es mono o tiene forma extraña
        mono_data = indata.flatten() if len(indata.shape) > 1 else indata
    
    # Añadir al stream si hay suficiente nivel de audio
    audio_level = np.max(np.abs(mono_data))
    if audio_level > 0.0005:  # Umbral más bajo para Bluetooth
        try:
            # Convertir a float64 para procesamiento interno
            audio_stream.put_nowait(mono_data.astype(np.float64))
        except queue.Full:
            # Si la cola está llena, remover el más viejo
            try:
                audio_stream.get_nowait()
                audio_stream.put_nowait(mono_data.astype(np.float64))
            except:
                pass

def start_audio_stream():
    """Iniciar stream continuo de audio"""
    global stream
    try:
        # Detectar automáticamente el mejor dispositivo
        best_device = get_best_audio_device()
        device_info = sd.query_devices(best_device)
        print(f"🎯 Usando dispositivo: {device_info['name']}")
        
        stream = sd.InputStream(
            samplerate=FS_CAPTURE,
            channels=min(CHANNELS_CAPTURE, device_info['max_input_channels']),  # Ajustar canales
            device=best_device,
            callback=audio_stream_callback,
            blocksize=CHUNK_SIZE,
            dtype='float32'  # Formato compatible
        )
        stream.start()
        print("🎵 Stream de audio iniciado correctamente")
        
    except Exception as e:
        print(f"❌ Error iniciando stream: {e}")
        # Fallback a device original
        try:
            print("🔄 Intentando con dispositivo original...")
            device_info = sd.query_devices(DEVICE_ID)
            stream = sd.InputStream(
                samplerate=FS_CAPTURE,
                channels=CHANNELS_CAPTURE,
                device=DEVICE_ID,
                callback=audio_stream_callback,
                blocksize=CHUNK_SIZE,
                dtype='float32'
            )
            stream.start()
            print("🎵 Stream iniciado con dispositivo de respaldo")
        except Exception as e2:
            print(f"❌ Error total: {e2}")
            raise

def stop_audio_stream():
    """Detener stream de audio"""
    global stream
    if 'stream' in globals() and stream:
        stream.stop()
        stream.close()
        print("🛑 Stream de audio detenido")

# Hilo: procesamiento con contexto conversacional
def contextual_audio_processor():
    """Procesa audio manteniendo contexto de la conversación"""
    global audio_buffer, last_transcription_time
    
    window_frames = int(FS_CAPTURE * AUDIO_WINDOW_SECONDS)  # 15 segundos de audio
    overlap_frames = int(FS_CAPTURE * CONTEXT_OVERLAP_SECONDS)  # 5 segundos overlap
    
    while not stop_flag.is_set():
        try:
            # Obtener chunk de audio del stream
            chunk = audio_stream.get(timeout=0.1)
            
            with buffer_lock:
                # Añadir al buffer acumulativo
                audio_buffer = np.concatenate([audio_buffer, chunk])
                
                # Verificar si tenemos suficiente audio para una ventana completa
                if len(audio_buffer) >= window_frames:
                    current_time = time.time()
                    
                    # Tomar ventana de 15 segundos
                    window_audio = audio_buffer[:window_frames].copy()
                    
                    # Mantener overlap de 5 segundos para la próxima ventana
                    audio_buffer = audio_buffer[window_frames - overlap_frames:]
                    
                    # Solo procesar si ha pasado tiempo suficiente (evitar spam)
                    if current_time - last_transcription_time >= 3:  # Mínimo 3 segundos entre transcripciones
                        # Resample y enviar a transcripción
                        audio_16k = resample_audio(window_audio, FS_CAPTURE, FS_MODEL)
                        
                        # Crear archivo temporal
                        ts = int(current_time * 1000)
                        tmp_path = f"temp_context_{ts}.wav"
                        sf.write(tmp_path, audio_16k, FS_MODEL, subtype='PCM_16')
                        
                        # Enviar con información de contexto
                        context_info = {
                            'audio_file': tmp_path,
                            'timestamp': current_time,
                            'window_seconds': AUDIO_WINDOW_SECONDS
                        }
                        
                        try:
                            text_stream.put_nowait(context_info)
                            last_transcription_time = current_time
                            
                            root.after(0, lambda: label_status.config(
                                text=f"Estado: Procesando ventana de {AUDIO_WINDOW_SECONDS}s con contexto 🧠", fg="#3498db"))
                        except queue.Full:
                            # Remover el más viejo si la cola está llena
                            try:
                                old_context = text_stream.get_nowait()
                                try:
                                    os.remove(old_context['audio_file'])
                                except:
                                    pass
                                text_stream.put_nowait(context_info)
                            except:
                                pass
                    
        except queue.Empty:
            continue
        except Exception as e:
            print(f"Error en procesador contextual: {e}")

def resample_audio(audio_data, fs_in, fs_out):
    """Resample audio de manera eficiente"""
    if fs_in == fs_out:
        return audio_data.astype(np.float32)
    
    ratio = fs_out / fs_in
    new_len = int(len(audio_data) * ratio)
    x_old = np.linspace(0, 1, len(audio_data), endpoint=False)
    x_new = np.linspace(0, 1, new_len, endpoint=False)
    resampled = np.interp(x_new, x_old, audio_data)
    return resampled.astype(np.float32)

# Hilo: transcripción contextual con Whisper
def contextual_transcribe_loop():
    """Transcribir audio manteniendo contexto conversacional"""
    global conversation_context
    
    while not stop_flag.is_set():
        try:
            # Obtener información contextual del stream
            context_info = text_stream.get(timeout=0.5)
        except queue.Empty:
            continue
        
        try:
            # Crear prompt de contexto basado en transcripciones anteriores
            context_prompt = ""
            if conversation_context:
                # Usar las últimas 3 transcripciones como contexto
                recent_context = conversation_context[-3:]
                context_prompt = " ".join(recent_context) + " "
                context_prompt = f"Previous conversation: {context_prompt}Continue the conversation:"
            else:
                context_prompt = "This is the beginning of a conversation in English:"
            
            # Transcribir con Whisper usando contexto
            print(f"🧠 Transcribiendo ventana de {AUDIO_WINDOW_SECONDS}s con contexto...")
            result = model.transcribe(
                context_info['audio_file'], 
                language="en", 
                fp16=False, 
                task="transcribe", 
                verbose=False,
                initial_prompt=context_prompt,
                condition_on_previous_text=True  # Usar contexto anterior
            )
            
            text = result.get("text", "").strip()
            
            if text and len(text) > 5:  # Filtro para textos significativos
                # Limpiar repeticiones comunes
                if not is_repetitive_text(text):
                    print(f"🎤 Transcripción contextual: '{text}'")
                    
                    # Añadir al contexto conversacional
                    conversation_context.append(text)
                    
                    # Mantener solo el contexto reciente
                    if len(conversation_context) > MAX_CONTEXT_HISTORY:
                        conversation_context = conversation_context[-MAX_CONTEXT_HISTORY:]
                    
                    # Crear texto acumulativo para mostrar
                    display_text = " ".join(conversation_context[-3:])  # Últimas 3 frases
                    
                    # Actualizar UI inmediatamente
                    root.after(0, lambda t=display_text: label_original.config(text=t))
                    
                    # Enviar a traducción con contexto
                    translation_context_info = {
                        'text': text,
                        'full_context': display_text,
                        'timestamp': context_info['timestamp']
                    }
                    
                    try:
                        translation_stream.put_nowait(translation_context_info)
                    except queue.Full:
                        try:
                            translation_stream.get_nowait()
                            translation_stream.put_nowait(translation_context_info)
                        except:
                            pass
                else:
                    print(f"⏭️ Texto repetitivo ignorado: '{text}'")
            else:
                print(f"⏭️ Texto muy corto ignorado: '{text}'")
                
        except Exception as e:
            print(f"Error en transcripción contextual: {e}")
        finally:
            # Limpiar archivo temporal
            try:
                os.remove(context_info['audio_file'])
            except:
                pass

def is_repetitive_text(text):
    """Detectar si el texto es repetitivo o sin sentido"""
    repetitive_phrases = [
        'thank you', 'thanks', 'you', 'the', 'and', 'a', 'an', 'this', 'that',
        'is', 'was', 'are', 'were', 'be', 'been', 'have', 'has', 'had'
    ]
    
    text_lower = text.lower().strip()
    
    # Si es solo una palabra repetitiva
    if text_lower in repetitive_phrases:
        return True
    
    # Si es muy corto y común
    if len(text_lower) < 10 and any(phrase in text_lower for phrase in repetitive_phrases[:5]):
        return True
    
    return False

# Hilo: traducción contextual
def contextual_translation_loop():
    """Traducir manteniendo contexto conversacional"""
    global translation_context
    
    while not stop_flag.is_set():
        try:
            # Obtener información contextual de traducción
            context_info = translation_stream.get(timeout=0.5)
        except queue.Empty:
            continue
        
        try:
            english_text = context_info['text']
            full_context = context_info['full_context']
            
            print(f"🔄 Traduciendo con contexto: '{english_text}'")
            
            # Traducir el texto actual
            spanish_text = translator.translate(english_text)
            print(f"✅ Traducción: '{spanish_text}'")
            
            # Añadir al contexto de traducciones
            translation_context.append(spanish_text)
            
            # Mantener contexto limitado
            if len(translation_context) > MAX_CONTEXT_HISTORY:
                translation_context = translation_context[-MAX_CONTEXT_HISTORY:]
            
            # Crear texto de traducción acumulativo
            display_translation = " ".join(translation_context[-3:])  # Últimas 3 traducciones
            
            # Actualizar UI con contexto completo
            root.after(0, lambda t=display_translation: label_translation.config(text=t))
            root.after(0, lambda: label_status.config(text="Estado: 🧠 Traducción contextual", fg="#27ae60"))
            
        except Exception as e:
            print(f"Error en traducción contextual: {e}")
            root.after(0, lambda: label_status.config(text="Error de traducción", fg="#e74c3c"))

# Funciones de control para contexto conversacional
def start_transcription():
    """Iniciar captura y traducción contextual"""
    global transcribing, conversation_context, translation_context, audio_buffer, last_transcription_time
    if transcribing:
        return
    
    # Limpiar contexto previo
    conversation_context.clear()
    translation_context.clear()
    last_transcription_time = 0
    
    with buffer_lock:
        audio_buffer = np.array([], dtype=np.float64)
    
    # Limpiar colas
    while not audio_stream.empty():
        try:
            audio_stream.get_nowait()
        except:
            break
    while not text_stream.empty():
        try:
            context_info = text_stream.get_nowait()
            try:
                os.remove(context_info['audio_file'])
            except:
                pass
        except:
            break
    while not translation_stream.empty():
        try:
            translation_stream.get_nowait()
        except:
            break
    
    transcribing = True
    stop_flag.clear()
    
    # Diagnóstico inicial
    diagnose_audio()
    
    try:
        # Iniciar stream de audio continuo
        start_audio_stream()
        
        # Iniciar hilos de procesamiento contextual
        threading.Thread(target=contextual_audio_processor, daemon=True).start()
        threading.Thread(target=contextual_transcribe_loop, daemon=True).start()
        threading.Thread(target=contextual_translation_loop, daemon=True).start()
        
        label_status.config(text=f"Estado: 🧠 Conversación contextual iniciada ({AUDIO_WINDOW_SECONDS}s ventanas)", fg="#27ae60")
        
    except Exception as e:
        label_status.config(text=f"Error al iniciar: {str(e)[:50]}", fg="#e74c3c")
        transcribing = False

def stop_transcription():
    """Detener captura y traducción"""
    global transcribing, conversation_context, translation_context
    stop_flag.set()
    transcribing = False
    
    # Detener stream
    stop_audio_stream()
    
    # Mostrar resumen final
    if conversation_context:
        print("=== RESUMEN DE CONVERSACIÓN ===")
        print("INGLÉS:", " ".join(conversation_context[-5:]))
        if translation_context:
            print("ESPAÑOL:", " ".join(translation_context[-5:]))
        print("=" * 40)
    
    label_status.config(text="Estado: Detenido", fg="#e74c3c")
    label_original.config(text="El audio transcrito aparecerá aquí...")
    label_translation.config(text="La traducción aparecerá aquí...")

def diagnose_devices():
    """Función para diagnosticar dispositivos desde la UI"""
    diagnose_audio()
    label_status.config(text="Ver consola para dispositivos disponibles", fg="#3498db")

# Botones de control
button_frame = tk.Frame(root, bg="#2c3e50")
button_frame.pack(pady=15)

btn_start = tk.Button(button_frame, text="🧠 Iniciar Conversación", command=start_transcription,
                     font=("Arial", 12, "bold"), bg="#27ae60", fg="white", 
                     padx=20, pady=10, relief="flat")
btn_start.pack(side="left", padx=10)

btn_stop = tk.Button(button_frame, text="⏹ Detener", command=stop_transcription,
                    font=("Arial", 12, "bold"), bg="#e74c3c", fg="white", 
                    padx=20, pady=10, relief="flat")
btn_stop.pack(side="left", padx=10)

btn_diagnose = tk.Button(button_frame, text="🔧 Diagnosticar Audio", command=diagnose_devices,
                        font=("Arial", 10), bg="#9b59b6", fg="white", 
                        padx=15, pady=10, relief="flat")
btn_diagnose.pack(side="left", padx=10)

# Info footer
info_label = tk.Label(root, text="🧠 Ventanas de 15s con contexto conversacional - Mantiene historial de la conversación", 
                     font=("Arial", 9), fg="#95a5a6", bg="#2c3e50")
info_label.pack(side="bottom", pady=5)

if __name__ == "__main__":
    root.mainloop()