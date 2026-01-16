# 🎧 Traductor de Audio en Tiempo Real

Aplicación de escritorio que captura audio del sistema y lo traduce del inglés al español en tiempo real usando inteligencia artificial.

## 🚀 Características

- ✨ **Transcripción en tiempo real** con Whisper AI
- 🌍 **Traducción automática** inglés → español
- 🎨 **Interfaz moderna** con tema oscuro
- 📊 **Bandeja del sistema** para uso discreto
- ⚡ **Procesamiento rápido** por fragmentos de audio

## 📋 Requisitos

- Python 3.8+
- Dispositivo de audio configurado (loopback)
- Conexión a internet (para traducción)

## 🛠️ Instalación

1. **Clonar/descargar el proyecto**
```bash
cd tradutorAudioSystem
```

2. **Crear entorno virtual**
```bash
python -m venv venv
venv\Scripts\activate  # Windows
# o source venv/bin/activate  # Linux/Mac
```

3. **Instalar dependencias**
```bash
pip install -r requirements.txt
```

4. **Ejecutar la aplicación**
```bash
python main.py
```

## ⚙️ Configuración

### Audio
- Ajusta `DEVICE_ID` en `config.py` según tu dispositivo de audio
- Para encontrar tu dispositivo: ejecuta `python -c "import sounddevice; print(sounddevice.query_devices())"`

### Modelos
- **Whisper**: Cambia el tamaño del modelo en `config.py` 
  - `tiny`: Más rápido, menos preciso
  - `small`: Balance entre velocidad y precisión ⭐ 
  - `medium/large`: Más preciso, más lento

## 🎯 Uso

1. **Iniciar**: Haz clic en "🎤 Iniciar Traducción"
2. **Reproducir**: Pon audio en inglés en tu sistema
3. **Ver**: La transcripción y traducción aparecen automáticamente
4. **Detener**: Haz clic en "⏹ Detener"

## 📁 Estructura del Proyecto

```
tradutorAudioSystem/
├── main.py           # Aplicación principal
├── config.py         # Configuración
├── requirements.txt  # Dependencias
├── README.md         # Este archivo
└── venv/            # Entorno virtual
```

## 🔧 Personalización

### Cambiar idiomas
En `config.py`, modifica:
```python
TRANSLATION_CONFIG = {
    'source_language': 'en',  # Idioma origen
    'target_language': 'es',  # Idioma destino
}
```

### Mejorar precisión
1. Usa un modelo Whisper más grande
2. Ajusta `chunk_seconds` (fragmentos más largos = mejor contexto)
3. Configura mejor el dispositivo de audio

## ❓ Preguntas Frecuentes

**P: ¿Necesito entrenar un modelo de IA?**
R: No. Usamos Whisper (OpenAI) para transcripción y Google Translate para traducción. Ambos están preentrenados.

**P: ¿Funciona sin internet?**
R: La transcripción sí (Whisper es local), pero la traducción requiere internet.

**P: ¿Puedo mejorar la traducción?**
R: Sí, en el futuro se puede integrar DeepL o Azure Translator para mejor calidad.

## 🐛 Solución de Problemas

- **No detecta audio**: Verifica `DEVICE_ID` en config.py
- **Traducción lenta**: Usa fragmentos de audio más cortos
- **Error de módulos**: Reinstala requirements.txt

## 🔮 Futuras Mejoras

- [ ] Soporte para más idiomas
- [ ] Integración con DeepL API
- [ ] Guardar traducciones
- [ ] Hotkeys globales
- [ ] Configuración visual

---
💡 **Tip**: Para mejor rendimiento, usa auriculares para evitar retroalimentación de audio.