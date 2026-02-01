import os
import time
import threading
from flask import Flask, request
import requests
from cerebro_chatgpt import interpretar_gasto, normalizar_cuenta, transcribir_audio
# from cerebro_sheets import guardar_en_sheets  <-- ESTO YA NO SE USA
from cerebro_supabase import guardar_gasto    # <-- ESTO ES LO NUEVO

app = Flask(__name__)

# --- TUS DATOS ---
TOKEN_WHATSAPP = os.getenv("TOKEN_WHATSAPP")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "un_secreto_cualquiera_123")

memoria_usuarios = {} 
mensajes_procesados = {} 

# --- FUNCIÓN: DESCARGAR AUDIO ---
def descargar_audio_whatsapp(media_id):
    try:
        url_info = f"https://graph.facebook.com/v21.0/{media_id}"
        headers = {"Authorization": f"Bearer {TOKEN_WHATSAPP}"}
        resp_info = requests.get(url_info, headers=headers)
        
        if resp_info.status_code != 200:
            print(f"❌ Error info media: {resp_info.text}")
            return None
            
        url_media = resp_info.json().get("url")
        headers_media = {"Authorization": f"Bearer {TOKEN_WHATSAPP}", "User-Agent": "Mozilla/5.0"}
        resp_media = requests.get(url_media, headers=headers_media)
        
        nombre_archivo = f"audio_{media_id}.ogg"
        with open(nombre_archivo, "wb") as f:
            f.write(resp_media.content)
        return nombre_archivo
    except Exception as e:
        print(f"❌ Error descarga: {e}")
        return None

# --- CEREBRO EN SEGUNDO PLANO ---
def procesar_mensaje_background(numero, texto_usuario, tipo_mensaje, mensaje_id, audio_id=None):
    print(f"🔄 Procesando en segundo plano... (Tipo: {tipo_mensaje})")
    
    # --- BLOQUE DE AUDIO ---
    if (tipo_mensaje == "audio" or tipo_mensaje == "voice") and audio_id:
        enviar_whatsapp(numero, "🎧 Escuchando...")
        archivo_temporal = descargar_audio_whatsapp(audio_id)
        
        if archivo_temporal:
            texto_transcrito = transcribir_audio(archivo_temporal)
            print(f"🗣️ Transcripción: {texto_transcrito}")
            try:
                os.remove(archivo_temporal)
            except:
                pass
            texto_usuario = texto_transcrito 
        else:
            enviar_whatsapp(numero, "❌ Error al descargar audio.")
            return
    # -----------------------

    try:
        if not texto_usuario:
            enviar_whatsapp(numero, "🤷‍♂️ Audio vacío o no se escuchó nada.")
            return

        # CASO A: EL USUARIO ESTÁ RESPONDIENDO QUÉ CUENTA USÓ
        if numero in memoria_usuarios:
            gasto_pendiente = memoria_usuarios[numero]
            cuenta_limpia = normalizar_cuenta(texto_usuario)
            gasto_pendiente['cuenta'] = cuenta_limpia
            
            # --- CAMBIO AQUÍ ---
            exito = guardar_gasto(gasto_pendiente) 
            # -------------------

            del memoria_usuarios[numero]
            
            if exito:
                enviar_whatsapp(numero, f"✅ Listo. ${gasto_pendiente['monto']} en **{cuenta_limpia}** (Guardado en Nube ☁️).")
            else:
                enviar_whatsapp(numero, "❌ Hubo un error guardando en Supabase.")
        
        # CASO B: MENSAJE NUEVO
        else:
            respuesta_ia = interpretar_gasto(texto_usuario)
            if respuesta_ia.get("gastos"):
                gasto = respuesta_ia["gastos"][0]
                
                if gasto['monto'] == 0:
                    enviar_whatsapp(numero, f"👂 Escuché: '{texto_usuario}'\n🤷‍♂️ Pero no entendí el monto.")
                
                elif not gasto.get('cuenta'):
                    memoria_usuarios[numero] = gasto
                    enviar_whatsapp(numero, f"🤔 Entendido: {gasto['item']} (${gasto['monto']}).\n\n¿Con qué pagaste?")
                
                else:
                    # --- CAMBIO AQUÍ ---
                    exito = guardar_gasto(gasto)
                    # -------------------

                    if exito:
                        enviar_whatsapp(numero, f"✅ Listo! {gasto['item']} (${gasto['monto']}) anotado en {gasto['cuenta']}.")
                    else:
                        enviar_whatsapp(numero, "❌ Error guardando en la base de datos.")
            else:
                enviar_whatsapp(numero, "👋 No entendí si es un gasto.")

    except Exception as e:
        print(f"❌ Error lógica: {e}")

# --- WEBHOOK ---
@app.route("/webhook", methods=["GET"])
def verificar_token():
    if request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge")
    return "Token inválido", 403

@app.route("/webhook", methods=["POST"])
def recibir_mensaje():
    datos = request.get_json()
    try:
        if datos.get("object") == "whatsapp_business_account":
            entrada = datos["entry"][0]["changes"][0]["value"]
            if "messages" in entrada:
                mensaje = entrada["messages"][0]
                msg_id = mensaje["id"]
                
                if msg_id in mensajes_procesados:
                    return "EVENT_RECEIVED", 200
                mensajes_procesados[msg_id] = True
                
                numero = mensaje["from"]
                tipo = mensaje["type"]
                
                print(f"👀 MENSAJE RECIBIDO DE {numero}. TIPO: '{tipo}'")
                
                texto_usuario = ""
                audio_id = None
                
                if tipo == "text":
                    texto_usuario = mensaje["text"]["body"]
                elif tipo == "audio":
                    audio_id = mensaje["audio"]["id"]
                elif tipo == "voice": 
                    audio_id = mensaje["voice"]["id"]
                
                if texto_usuario or audio_id:
                    hilo = threading.Thread(target=procesar_mensaje_background, args=(numero, texto_usuario, tipo, msg_id, audio_id))
                    hilo.start()
                else:
                    print(f"⚠️ Mensaje ignorado porque no es texto ni audio (es {tipo})")

        return "EVENT_RECEIVED", 200
    except Exception as e:
        print(f"❌ Error crítico webhook: {e}")
        return "EVENT_RECEIVED", 200

def enviar_whatsapp(numero, texto):
    url = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {TOKEN_WHATSAPP}", "Content-Type": "application/json"}
    data = {"messaging_product": "whatsapp", "to": numero, "type": "text", "text": {"body": texto}}
    requests.post(url, headers=headers, json=data)

if __name__ == "__main__":
    app.run(port=5000)