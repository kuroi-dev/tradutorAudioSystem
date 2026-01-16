"""
Configuración del Traductor de Audio en Tiempo Real
"""

# Configuración de audio
AUDIO_CONFIG = {
    'sample_rate_capture': 44100,
    'sample_rate_model': 16000,
    'channels': 2,
    'device_id': 14,  # Mezcla estéreo Realtek DirectSound - ajustar según tu sistema
    'chunk_seconds': 3,
    'silence_threshold': 0.01
}

# Configuración del modelo Whisper
WHISPER_CONFIG = {
    'model_size': 'small',  # 'tiny', 'base', 'small', 'medium', 'large'
    'language': 'en',
    'fp16': False
}

# Configuración de traducción
TRANSLATION_CONFIG = {
    'source_language': 'en',
    'target_language': 'es',
    'service': 'google'  # 'google', 'deepl' (futuro)
}

# Configuración de UI
UI_CONFIG = {
    'window_width': 800,
    'window_height': 400,
    'theme': 'dark',
    'colors': {
        'bg_primary': '#2c3e50',
        'bg_secondary': '#34495e',
        'accent_blue': '#3498db',
        'accent_green': '#27ae60',
        'accent_red': '#e74c3c',
        'accent_orange': '#f39c12',
        'text_light': '#ecf0f1',
        'text_muted': '#95a5a6'
    }
}