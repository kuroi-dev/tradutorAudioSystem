#!/usr/bin/env python3
"""
Sistema Híbrido de Traducción de Audio EN→ES
- Traducción en tiempo real (sin contexto, cada 3s)
- Análisis contextual completo (cada 15 minutos)
- Detección de pausas para respetar el habla natural
"""

import tkinter as tk
from tkinter import scrolledtext
import sounddevice as sd
import soundfile as sf
import whisper
import numpy as np
import queue
import threading
import time as time_module
import os
import pystray
from PIL import Image, ImageDraw
from deep_translator import GoogleTranslator

import config

# Configuración de Whisper y Traductor
print("🚀 Cargando modelos...")
whisper_model = whisper.load_model("base")
translator = GoogleTranslator(source='en', target='es')
print("✅ Modelos cargados")

# Variables globales para el sistema híbrido dual
audio_stream = queue.Queue(maxsize=50)
realtime_queue = queue.Queue(maxsize=10)
context_queue = queue.Queue(maxsize=5)
transcribing = False
stop_flag = threading.Event()

# Buffers duales
realtime_buffer = np.array([], dtype=np.float64)
context_buffer = np.array([], dtype=np.float64)
buffer_lock = threading.Lock()

# Control de tiempo
last_realtime_process = 0
last_context_process = 0
context_start_time = 0

# Detector de pausas
silence_start_time = 0
is_in_silence = False

# Configuración de la ventana principal
root = tk.Tk()
root.title("🎯 Traductor Híbrido EN→ES - Tiempo Real + Contexto")
root.geometry("900x800")
root.configure(bg="#2c3e50")
root.iconbitmap(default="nul")

# Estilo UI
title_label = tk.Label(root, text="⚡ Sistema Híbrido: Tiempo Real + Contexto Conversacional", 
                      font=("Arial", 16, "bold"), fg="#ecf0f1", bg="#2c3e50")
title_label.pack(pady=10)

status_label = tk.Label(root, text="Sistema detenido", font=("Arial", 12), 
                       fg="#e74c3c", bg="#2c3e50")
status_label.pack(pady=5)

# Control Frame
control_frame = tk.Frame(root, bg="#2c3e50")
control_frame.pack(pady=10)

start_button = tk.Button(control_frame, text="▶️ Iniciar Sistema Híbrido", 
                        font=("Arial", 12, "bold"), bg="#27ae60", fg="white",
                        command=lambda: start_hybrid_system())
start_button.pack(side=tk.LEFT, padx=5)

stop_button = tk.Button(control_frame, text="⏹️ Detener", 
                       font=("Arial", 12, "bold"), bg="#e74c3c", fg="white",
                       command=lambda: stop_hybrid_system())
stop_button.pack(side=tk.LEFT, padx=5)

# Área de texto con scroll
text_frame = tk.Frame(root, bg="#2c3e50")
text_frame.pack(pady=10, padx=20, fill="both", expand=True)

text_area = scrolledtext.ScrolledText(text_frame, 
                                     width=100, height=30,
                                     font=("Courier", 10),
                                     bg="#34495e", fg="#ecf0f1",
                                     state=tk.DISABLED)
text_area.pack(fill="both", expand=True)

def audio_callback(indata, frames, time, status):
    """Callback de audio que procesa el stream continuo con detector de pausas"""
    global realtime_buffer, context_buffer, last_realtime_process, last_context_process
    global silence_start_time, is_in_silence, context_start_time
    
    if stop_flag.is_set():
        return
    
    if status:
        print(f"Audio callback status: {status}")
    
    # Convertir audio y detectar nivel de volumen
    audio_data = indata[:, 0] if indata.ndim > 1 else indata
    audio_level = np.sqrt(np.mean(audio_data**2))
    
    # Detector de pausas/silencio
    current_time = time_module.time()
    
    if audio_level < config.SILENCE_THRESHOLD:
        if not is_in_silence:
            silence_start_time = current_time
            is_in_silence = True
    else:
        is_in_silence = False
    
    # Solo procesar si no estamos en una pausa activa
    silence_duration = current_time - silence_start_time if is_in_silence else 0
    
    try:
        with buffer_lock:
            # Agregar a ambos buffers
            realtime_buffer = np.concatenate([realtime_buffer, audio_data])
            context_buffer = np.concatenate([context_buffer, audio_data])
            
            # Procesar tiempo real cada 3 segundos (si no hay pausa activa)
            if (current_time - last_realtime_process >= config.REALTIME_WINDOW_SECONDS and 
                not (is_in_silence and silence_duration < config.SILENCE_DURATION)):
                
                if len(realtime_buffer) > 0:
                    # Copiar buffer para procesamiento
                    process_buffer = realtime_buffer.copy()
                    
                    # Limpiar buffer para tiempo real
                    realtime_buffer = np.array([], dtype=np.float64)
                    last_realtime_process = current_time
                    
                    # Agregar a cola sin bloquear
                    try:
                        realtime_queue.put(('realtime', process_buffer), block=False)
                    except queue.Full:
                        pass
            
            # Procesar contexto cada 15 minutos
            context_interval_seconds = config.CONTEXT_INTERVAL_MINUTES * 60
            if current_time - last_context_process >= context_interval_seconds:
                if len(context_buffer) > 0:
                    # Copiar buffer completo para análisis contextual
                    full_context_buffer = context_buffer.copy()
                    
                    # Guardar tiempo de inicio para referencia
                    context_period = context_start_time if context_start_time > 0 else last_context_process
                    last_context_process = current_time
                    
                    # Reset buffer contextual para siguiente período
                    context_buffer = np.array([], dtype=np.float64)
                    context_start_time = current_time
                    
                    # Agregar a cola contextual
                    try:
                        context_queue.put(('context', full_context_buffer, context_period, current_time), block=False)
                    except queue.Full:
                        pass
                        
    except Exception as e:
        print(f"Error en audio callback: {e}")

def realtime_processor():
    """Procesa audio en tiempo real (sin contexto)"""
    while not stop_flag.is_set():
        try:
            # Obtener audio de la cola
            queue_item = realtime_queue.get(timeout=1)
            if queue_item is None:
                break
                
            process_type, audio_data = queue_item
            
            if len(audio_data) == 0:
                continue
            
            # Transcribir audio
            temp_file = "temp_realtime_audio.wav"
            sf.write(temp_file, audio_data, config.SAMPLE_RATE)
            
            print(f"🎤 Procesando tiempo real... ({len(audio_data)/config.SAMPLE_RATE:.1f}s)")
            
            result = whisper_model.transcribe(
                temp_file,
                language="en",
                task="transcribe",
                fp16=False,
                verbose=False
            )
            
            text = result["text"].strip()
            if text:
                print(f"📝 Transcripción RT: {text}")
                
                # Traducir inmediatamente
                try:
                    translated = translator.translate(text)
                    print(f"🔄 Traducción RT: {translated}")
                    
                    # Actualizar GUI con resultado en tiempo real
                    update_gui_realtime(text, translated)
                    
                except Exception as e:
                    print(f"Error traduciendo tiempo real: {e}")
            
            # Limpiar archivo temporal
            try:
                os.remove(temp_file)
            except:
                pass
                
        except queue.Empty:
            continue
        except Exception as e:
            print(f"Error en procesador tiempo real: {e}")

def context_processor():
    """Procesa contexto completo cada 15 minutos"""
    while not stop_flag.is_set():
        try:
            # Obtener contexto de la cola
            queue_item = context_queue.get(timeout=1)
            if queue_item is None:
                break
                
            process_type, audio_data, start_time, end_time = queue_item
            duration_minutes = (end_time - start_time) / 60
            
            if len(audio_data) == 0:
                continue
            
            print(f"\n🧠 PROCESANDO CONTEXTO COMPLETO ({duration_minutes:.1f} minutos)")
            
            # Transcribir todo el contexto
            temp_file = "temp_context_audio.wav"
            sf.write(temp_file, audio_data, config.SAMPLE_RATE)
            
            result = whisper_model.transcribe(
                temp_file,
                language="en",
                task="transcribe",
                fp16=False,
                verbose=True
            )
            
            full_text = result["text"].strip()
            
            if full_text:
                print(f"📚 Transcripción contextual: {full_text[:200]}...")
                
                # Traducir con contexto completo
                try:
                    contextual_translation = translator.translate(full_text)
                    print(f"🎯 Traducción contextual: {contextual_translation[:200]}...")
                    
                    # Actualizar GUI con análisis contextual
                    update_gui_context(full_text, contextual_translation, duration_minutes)
                    
                except Exception as e:
                    print(f"Error en traducción contextual: {e}")
            
            # Limpiar archivo temporal
            try:
                os.remove(temp_file)
            except:
                pass
                
        except queue.Empty:
            continue
        except Exception as e:
            print(f"Error en procesador contextual: {e}")

def update_gui_realtime(text, translation):
    """Actualiza GUI con resultado en tiempo real"""
    def update():
        text_area.config(state=tk.NORMAL)
        timestamp = time_module.strftime("%H:%M:%S")
        text_area.insert(tk.END, f"⚡ [{timestamp}] RT: {text} → {translation}\n")
        text_area.see(tk.END)
        text_area.config(state=tk.DISABLED)
        
        status_label.config(text=f"⚡ Tiempo real activo | Último: {text[:30]}...")
    
    root.after(0, update)

def update_gui_context(text, translation, duration):
    """Actualiza GUI con análisis contextual"""
    def update():
        text_area.config(state=tk.NORMAL)
        timestamp = time_module.strftime("%H:%M:%S")
        text_area.insert(tk.END, f"\n🧠 [{timestamp}] CONTEXTO ({duration:.1f}min):\n")
        text_area.insert(tk.END, f"📝 Original: {text[:100]}...\n")
        text_area.insert(tk.END, f"🎯 Traducción contextual: {translation[:100]}...\n")
        text_area.insert(tk.END, "-" * 80 + "\n\n")
        text_area.see(tk.END)
        text_area.config(state=tk.DISABLED)
        
        status_label.config(text=f"🧠 Análisis contextual completado ({duration:.1f} min)")
    
    root.after(0, update)

def get_best_audio_device():
    """Encontrar el mejor dispositivo para capturar audio del sistema"""
    devices = sd.query_devices()
    
    # Prioridades para dispositivos (orden de preferencia)
    priorities = [
        "Microsoft Sound Mapper",
        "Primary Sound Capture",
        "Mezcla estéreo",
        "Stereo Mix"
    ]
    
    for priority in priorities:
        for i, device in enumerate(devices):
            if (device['max_input_channels'] > 0 and 
                priority.lower() in device['name'].lower()):
                print(f"✅ Dispositivo seleccionado: ID {i} - {device['name']}")
                return i
    
    # Si no encuentra ninguno, usar el primero disponible
    for i, device in enumerate(devices):
        if device['max_input_channels'] > 0:
            print(f"⚠️ Usando dispositivo por defecto: ID {i} - {device['name']}")
            return i
    
    raise Exception("No se encontró ningún dispositivo de entrada de audio")

def start_hybrid_system():
    """Iniciar el sistema híbrido de traducción"""
    global transcribing, last_realtime_process, last_context_process, context_start_time
    global realtime_buffer, context_buffer
    
    if transcribing:
        return
    
    try:
        # Resetear variables
        stop_flag.clear()
        transcribing = True
        
        current_time = time_module.time()
        last_realtime_process = current_time
        last_context_process = current_time
        context_start_time = current_time
        
        with buffer_lock:
            realtime_buffer = np.array([], dtype=np.float64)
            context_buffer = np.array([], dtype=np.float64)
        
        # Obtener mejor dispositivo
        device_id = get_best_audio_device()
        
        # Iniciar captura de audio
        stream = sd.InputStream(
            device=device_id,
            channels=1,
            samplerate=config.SAMPLE_RATE,
            dtype='float32',
            blocksize=1024,
            callback=audio_callback
        )
        
        # Iniciar procesadores en threads separados
        realtime_thread = threading.Thread(target=realtime_processor, daemon=True)
        context_thread = threading.Thread(target=context_processor, daemon=True)
        
        realtime_thread.start()
        context_thread.start()
        
        # Iniciar stream de audio
        stream.start()
        
        print("🎯 Sistema híbrido iniciado")
        print(f"⚡ Tiempo real: cada {config.REALTIME_WINDOW_SECONDS}s")
        print(f"🧠 Contexto: cada {config.CONTEXT_INTERVAL_MINUTES} minutos")
        print(f"🔇 Silencio: {config.SILENCE_DURATION}s @ {config.SILENCE_THRESHOLD}")
        
        # Actualizar UI
        start_button.config(state=tk.DISABLED)
        stop_button.config(state=tk.NORMAL)
        status_label.config(text="🎯 Sistema híbrido ACTIVO", fg="#27ae60")
        
        # Guardar referencia al stream
        root.audio_stream = stream
        
    except Exception as e:
        print(f"Error iniciando sistema: {e}")
        transcribing = False
        start_button.config(state=tk.NORMAL)
        stop_button.config(state=tk.DISABLED)
        status_label.config(text=f"❌ Error: {e}", fg="#e74c3c")

def stop_hybrid_system():
    """Detener el sistema híbrido"""
    global transcribing
    
    if not transcribing:
        return
    
    try:
        # Señalar detención
        stop_flag.set()
        transcribing = False
        
        # Detener stream de audio
        if hasattr(root, 'audio_stream'):
            root.audio_stream.stop()
            root.audio_stream.close()
            del root.audio_stream
        
        print("🛑 Sistema híbrido detenido")
        
        # Actualizar UI
        start_button.config(state=tk.NORMAL)
        stop_button.config(state=tk.DISABLED)
        status_label.config(text="🛑 Sistema detenido", fg="#e74c3c")
        
    except Exception as e:
        print(f"Error deteniendo sistema: {e}")

def create_tray_icon():
    """Crear icono para bandeja del sistema"""
    image = Image.new("RGB", (64, 64), "#2c3e50")
    dc = ImageDraw.Draw(image)
    dc.rectangle((16, 16, 48, 48), fill="#3498db")
    dc.text((20, 25), "🎯", fill="white")
    return image

def on_quit(icon, item):
    """Cerrar aplicación desde bandeja"""
    stop_flag.set()
    icon.stop()
    root.quit()

# Icono en bandeja del sistema
icon = pystray.Icon("TraductorHibrido", create_tray_icon(), 
                   menu=pystray.Menu(pystray.MenuItem("Salir", on_quit)))

def run_icon():
    icon.run()

# Iniciar icono en thread separado
threading.Thread(target=run_icon, daemon=True).start()

# Manejo de cierre de ventana
def on_closing():
    stop_hybrid_system()
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_closing)

if __name__ == "__main__":
    print("🎯 Sistema Híbrido de Traducción EN→ES")
    print("⚡ Tiempo real: Traducciones inmediatas cada 3 segundos")
    print("🧠 Contexto: Análisis completo cada 15 minutos")
    print("🔇 Detección de pausas automática")
    print("=" * 60)
    
    root.mainloop()