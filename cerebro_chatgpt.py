import os
import json
from openai import OpenAI
from datetime import datetime

# Configuración de la API Key
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def transcribir_audio(ruta_audio):
    """
    Toma la ruta de un archivo de audio (ogg/mp3/wav) y devuelve el texto transcrito usando Whisper.
    """
    print(f"🎤 Iniciando transcripción de: {ruta_audio}")
    try:
        with open(ruta_audio, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1", 
                file=audio_file,
                language="es"  # Forzamos español para mejor precisión
            )
            texto = transcript.text
            print(f"📝 Texto detectado: {texto}")
            return texto
    except Exception as e:
        print(f"❌ Error CRÍTICO en transcripción: {e}")
        return ""

def interpretar_gasto(mensaje):
    """
    Analiza el mensaje y extrae los datos del gasto (item, monto, cuenta).
    """
    hoy = datetime.now().strftime("%Y-%m-%d")
    
    prompt = f"""
    Eres un asistente contable experto. Tu única tarea es extraer datos de gastos de un texto informal.
    Hoy es: {hoy}.

    Analiza el siguiente texto: "{mensaje}"

    Reglas OBLIGATORIAS:
    1. Responde SOLO en formato JSON.
    2. El JSON debe tener esta estructura exacta:
       {{
         "gastos": [
           {{
             "fecha": "YYYY-MM-DD",
             "item": "descripcion breve",
             "monto": 12345 (numero entero, sin puntos ni signos),
             "cuenta": "nombre_cuenta_normalizado" (o null si no se menciona),
             "moneda": "CLP"
           }}
         ]
       }}
    3. Si el usuario menciona "ayer", calcula la fecha correcta.
    4. "Cuenta" debe normalizarse a una de estas si es posible: "Banco Falabella", "Santander", "Efectivo", "Tarjeta de Crédito", "Mercado Pago". Si no sabes, pon null.
    5. Si el monto es 0 o no aparece, pon 0.
    """

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Eres una API que solo responde JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0
        )
        
        contenido = response.choices[0].message.content
        # Limpieza por si GPT pone ```json ... ```
        contenido = contenido.replace("```json", "").replace("```", "").strip()
        
        datos = json.loads(contenido)
        return datos

    except Exception as e:
        print(f"❌ Error en GPT: {e}")
        return {"gastos": [{"item": "Error", "monto": 0, "cuenta": None}]}

def normalizar_cuenta(texto):
    """
    Intenta adivinar la cuenta basándose en palabras clave.
    """
    texto = texto.lower()
    if "falabella" in texto:
        return "Banco Falabella"
    elif "santander" in texto:
        return "Santander"
    elif "chile" in texto:
        return "Banco de Chile"
    elif "efectivo" in texto or "cash" in texto:
        return "Efectivo"
    elif "mercado" in texto:
        return "Mercado Pago"
    else:
        return "Banco Falabella" # Valor por defecto si no se sabe

