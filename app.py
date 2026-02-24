import os
import threading
from flask import Flask, request
import requests
# AGREGADO: 'analizar_consulta'
from cerebro_chatgpt import interpretar_gasto, normalizar_cuenta, transcribir_audio, analizar_consulta
# AGREGADO: 'obtener_ultimos_gastos'
from cerebro_supabase import guardar_gasto, supabase, obtener_ultimos_gastos

app = Flask(__name__)

# --- TUS DATOS ---
TOKEN_WHATSAPP = os.getenv("TOKEN_WHATSAPP")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "un_secreto_cualquiera_123")

memoria_usuarios = {} 
mensajes_procesados = {} 

# --- LA BIENVENIDA ---
@app.route("/")
def home():
    return "¡Hola! El bot de finanzas está VIVO y ESCUCHANDO 🤖🎧", 200

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

# --- CEREBRO EN SEGUNDO PLANO (MODIFICADO) ---
def procesar_mensaje_background(numero, texto_usuario, tipo_mensaje, mensaje_id, audio_id=None):
    print(f"🔄 Procesando... (Tipo: {tipo_mensaje})")
    
    # --- 1. BLOQUE DE AUDIO ---
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
            enviar_whatsapp(numero, "❌ No pude descargar el audio de WhatsApp.")
            return

    if not texto_usuario:
        return

    # --- 2. BLOQUE DE IDENTIDAD 🕵️‍♂️ ---
    user_id_detectado = None
    try:
        resp_usuario = supabase.table("usuarios_bot").select("user_id").eq("celular", numero).execute()
        if resp_usuario.data:
            user_id_detectado = resp_usuario.data[0]["user_id"]
            print(f"✅ Usuario Identificado: {user_id_detectado}")
        else:
            print(f"⚠️ Numero {numero} no tiene User ID asignado en 'usuarios_bot'")
    except Exception as e:
        print(f"❌ Error buscando identidad: {e}")

    # --- 3. LÓGICA DE GASTOS Y PREGUNTAS ---
    try:
        # CASO A: EL USUARIO ESTÁ RESPONDIENDO QUÉ CUENTA USÓ (Hilo de conversación)
        if numero in memoria_usuarios:
            gasto_pendiente = memoria_usuarios[numero]
            cuenta_limpia = normalizar_cuenta(texto_usuario)
            gasto_pendiente['cuenta'] = cuenta_limpia
            
            # INYECTAMOS EL ID
            gasto_pendiente['user_id'] = user_id_detectado

            exito = guardar_gasto(gasto_pendiente) 
            del memoria_usuarios[numero]
            
            if exito:
                enviar_whatsapp(numero, f"✅ Listo. ${gasto_pendiente['monto']} en **{cuenta_limpia}**.")
            else:
                enviar_whatsapp(numero, "❌ Hubo un error guardando en Supabase.")
        
        # CASO B: MENSAJE NUEVO
        else:
            respuesta_ia = interpretar_gasto(texto_usuario)
            
            # --- NUEVA LÓGICA: ¿ES PREGUNTA O GASTO? ---
            if respuesta_ia.get("intencion") == "pregunta":
                if not user_id_detectado:
                    enviar_whatsapp(numero, "🔒 Necesito saber quién eres para analizar tus datos. (Tu número no está registrado).")
                else:
                    enviar_whatsapp(numero, "🧐 Déjame revisar tus números...")
                    # 1. Traemos los datos de Supabase
                    datos_gastos = obtener_ultimos_gastos(user_id_detectado)
                    # 2. Analizamos con GPT
                    respuesta_analisis = analizar_consulta(texto_usuario, datos_gastos)
                    # 3. Respondemos
                    enviar_whatsapp(numero, respuesta_analisis)

            # --- LÓGICA ANTIGUA (Es un gasto) ---
            elif respuesta_ia.get("gastos"):
                gasto = respuesta_ia["gastos"][0]
                
                # INYECTAMOS EL ID
                gasto['user_id'] = user_id_detectado
                
                if gasto['monto'] == 0:
                    enviar_whatsapp(numero, f"👂 Escuché: '{texto_usuario}'\n🤷‍♂️ Pero no entendí el monto.")
                
                elif not gasto.get('cuenta'):
                    memoria_usuarios[numero] = gasto
                    enviar_whatsapp(numero, f"🤔 Entendido: {gasto['item']} (${gasto['monto']}).\n\n¿Con qué pagaste?")
                
                else:
                    exito = guardar_gasto(gasto)

                    if exito:
                        enviar_whatsapp(numero, f"✅ Listo! {gasto['item']} (${gasto['monto']}) anotado en {gasto['cuenta']}.")
                    else:
                        enviar_whatsapp(numero, "❌ Error guardando en la base de datos.")
            
            # CASO C: NO ENTENDIÓ NADA
            else:
                enviar_whatsapp(numero, "👋 No entendí si es un gasto o una pregunta.")

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

        return "EVENT_RECEIVED", 200
    except Exception as e:
        print(f"❌ Error webhook: {e}")
        return "EVENT_RECEIVED", 200

def enviar_whatsapp(numero, texto):
    try:
        url = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"
        headers = {"Authorization": f"Bearer {TOKEN_WHATSAPP}", "Content-Type": "application/json"}
        data = {"messaging_product": "whatsapp", "to": numero, "type": "text", "text": {"body": texto}}
        requests.post(url, headers=headers, json=data)
    except Exception as e:
        print(f"Error enviando Whatsapp: {e}")

if __name__ == "__main__":
    app.run(port=5000)