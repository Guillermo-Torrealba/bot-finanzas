# Actualizacion Audio V2
import os
import time
import threading # <--- IMPORTANTE: La herramienta para trabajar en paralelo
from flask import Flask, request
import requests
# --- AGREGAMOS transcribir_audio AQUI ---
from cerebro_chatgpt import interpretar_gasto, normalizar_cuenta, transcribir_audio
from cerebro_sheets import guardar_en_sheets

app = Flask(__name__)

# --- TUS DATOS ---
TOKEN_WHATSAPP = os.getenv("TOKEN_WHATSAPP")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "un_secreto_cualquiera_123")

# --- MEMORIA VOLÁTIL ---
memoria_usuarios = {} 
mensajes_procesados = {} 

# --- NUEVA FUNCIÓN: DESCARGAR AUDIO ---
def descargar_audio_whatsapp(media_id):
    try:
        # 1. Obtenemos la URL real del archivo
        url_info = f"https://graph.facebook.com/v21.0/{media_id}"
        headers = {"Authorization": f"Bearer {TOKEN_WHATSAPP}"}
        resp_info = requests.get(url_info, headers=headers)
        url_media = resp_info.json().get("url")
        
        # 2. Descargamos el contenido (bytes)
        resp_media = requests.get(url_media, headers=headers)
        
        # 3. Guardamos en un archivo temporal
        nombre_archivo = f"audio_{media_id}.ogg"
        with open(nombre_archivo, "wb") as f:
            f.write(resp_media.content)
            
        return nombre_archivo
    except Exception as e:
        print(f"Error descargando audio: {e}")
        return None

# --- FUNCIÓN QUE PIENSA (SEGUNDO PLANO) ---
# Ahora recibe 'tipo_mensaje' y 'audio_id'
def procesar_mensaje_background(numero, texto_usuario, tipo_mensaje, mensaje_id, audio_id=None):
    """
    Esta función corre en paralelo para no hacer esperar a Facebook.
    """
    print(f"🔄 Procesando en segundo plano...")

    # --- BLOQUE DE AUDIO ---
    if tipo_mensaje == "audio" and audio_id:
        enviar_whatsapp(numero, "🎧 Escuchando...")
        archivo_temporal = descargar_audio_whatsapp(audio_id)
        
        if archivo_temporal:
            # Transcribimos usando Whisper
            texto_transcrito = transcribir_audio(archivo_temporal)
            print(f"🗣️ Audio dice: {texto_transcrito}")
            
            # Borramos el archivo temporal para no llenar el disco
            try:
                os.remove(archivo_temporal)
            except:
                pass
            
            # ¡TRUCO! Convertimos el audio en texto y seguimos como si el usuario lo hubiera escrito
            texto_usuario = texto_transcrito
        else:
            enviar_whatsapp(numero, "❌ No pude descargar el audio.")
            return
    # -----------------------
    
    try:
        # Si el texto está vacío (audio fallido o mensaje vacío)
        if not texto_usuario:
            return

        # 1. ¿Es respuesta a una pregunta pendiente?
        if numero in memoria_usuarios:
            gasto_pendiente = memoria_usuarios[numero]
            cuenta_limpia = normalizar_cuenta(texto_usuario)
            gasto_pendiente['cuenta'] = cuenta_limpia
            
            guardar_en_sheets(gasto_pendiente)
            del memoria_usuarios[numero]
            enviar_whatsapp(numero, f"✅ Listo. ${gasto_pendiente['monto']} en **{cuenta_limpia}**.")
        
        # 2. Es un mensaje nuevo (Texto o Audio transcrito)
        else:
            respuesta_ia = interpretar_gasto(texto_usuario)
            if respuesta_ia.get("gastos"):
                gasto = respuesta_ia["gastos"][0]
                
                if gasto['monto'] == 0:
                    # Si venía de audio, le decimos qué escuchamos
                    msg_error = "🤷‍♂️ No entendí el monto."
                    if tipo_mensaje == "audio":
                        msg_error = f"👂 Escuché: '{texto_usuario}'\n🤷‍♂️ Pero no entendí el monto."
                    enviar_whatsapp(numero, msg_error)
                
                elif not gasto.get('cuenta'):
                    memoria_usuarios[numero] = gasto
                    enviar_whatsapp(numero, f"🤔 Entendido: {gasto['item']} (${gasto['monto']}).\n\n¿Con qué pagaste?")
                else:
                    guardar_en_sheets(gasto)
                    enviar_whatsapp(numero, f"✅ Listo! {gasto['item']} (${gasto['monto']}) anotado en {gasto['cuenta']}.")
            else:
                enviar_whatsapp(numero, "👋 Hola! Dime qué compraste.")

    except Exception as e:
        print(f"❌ Error en background: {e}")

# --- SERVIDOR WEB (PRIMER PLANO) ---
@app.route("/webhook", methods=["GET"])
def verificar_token():
    token_enviado = request.args.get("hub.verify_token")
    if token_enviado == VERIFY_TOKEN:
        return request.args.get("hub.challenge")
    return "Token inválido", 403

@app.route("/webhook", methods=["POST"])
def recibir_mensaje():
    datos = request.get_json()
    
    # Limpieza básica de memoria
    if len(mensajes_procesados) > 500:
        mensajes_procesados.clear()

    try:
        if datos.get("object") == "whatsapp_business_account":
            entrada = datos["entry"][0]["changes"][0]["value"]
            
            if "messages" in entrada:
                mensaje = entrada["messages"][0]
                msg_id = mensaje["id"]
                
                # --- ESCUDO ANTI-DUPLICADOS ---
                if msg_id in mensajes_procesados:
                    return "EVENT_RECEIVED", 200
                
                mensajes_procesados[msg_id] = True
                
                # Extraemos datos básicos
                numero = mensaje["from"]
                tipo = mensaje["type"]
                texto_usuario = ""
                audio_id = None
                
                # DETECTAMOS SI ES TEXTO O AUDIO
                if tipo == "text":
                    texto_usuario = mensaje["text"]["body"]
                elif tipo == "audio":
                    audio_id = mensaje["audio"]["id"]
                
                # Si hay texto O audio, lanzamos el hilo
                if texto_usuario or audio_id:
                    # --- LANZAMOS EL HILO ---
                    # Pasamos los nuevos argumentos: tipo y audio_id
                    hilo = threading.Thread(target=procesar_mensaje_background, args=(numero, texto_usuario, tipo, msg_id, audio_id))
                    hilo.start()

        # RESPONDEMOS A FACEBOOK EN MENOS DE 0.1 SEGUNDOS
        return "EVENT_RECEIVED", 200

    except Exception as e:
        print("Error en webhook:", e)
        return "EVENT_RECEIVED", 200

def enviar_whatsapp(numero, texto):
    url = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {TOKEN_WHATSAPP}", "Content-Type": "application/json"}
    data = {"messaging_product": "whatsapp", "to": numero, "type": "text", "text": {"body": texto}}
    requests.post(url, headers=headers, json=data)

if __name__ == "__main__":
    app.run(port=5000)