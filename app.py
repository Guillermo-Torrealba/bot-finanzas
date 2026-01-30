import os
import threading
from flask import Flask, request
import requests
from cerebro_chatgpt import interpretar_gasto, normalizar_cuenta, transcribir_audio, decidir_intencion, analizar_consultas_ia
from cerebro_sheets import guardar_en_sheets, obtener_gastos_mes_actual

app = Flask(__name__)

TOKEN_WHATSAPP = os.getenv("TOKEN_WHATSAPP")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "un_secreto_cualquiera_123")

memoria_usuarios = {} 
mensajes_procesados = {} 

@app.route("/")
def home():
    return "¡Hola! El bot de finanzas está VIVO y PENSANDO 🤖🧠", 200

def descargar_audio_whatsapp(media_id):
    try:
        url_info = f"https://graph.facebook.com/v21.0/{media_id}"
        headers = {"Authorization": f"Bearer {TOKEN_WHATSAPP}"}
        resp_info = requests.get(url_info, headers=headers)
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

def procesar_mensaje_background(numero, texto_usuario, tipo_mensaje, mensaje_id, audio_id=None):
    print(f"🔄 Procesando mensaje de {numero}...")
    
    # 1. SI ES AUDIO, TRANSCRIBIR PRIMERO
    if (tipo_mensaje == "audio" or tipo_mensaje == "voice") and audio_id:
        enviar_whatsapp(numero, "🎧 Escuchando...")
        archivo_temporal = descargar_audio_whatsapp(audio_id)
        if archivo_temporal:
            texto_transcrito = transcribir_audio(archivo_temporal)
            texto_usuario = texto_transcrito 
            try:
                os.remove(archivo_temporal)
            except: pass
        else:
            return

    if not texto_usuario:
        return

    try:
        # --- CORRECCIÓN CRÍTICA: MEMORIA PRIMERO ---
        # Antes de pensar con IA, revisamos si el usuario nos debía una respuesta.
        if numero in memoria_usuarios:
            print(f"📝 Usuario {numero} tenía algo pendiente. Completando...")
            gasto_pendiente = memoria_usuarios[numero]
            
            # Normalizamos lo que respondiste (ej: "debito" -> "Débito BICE")
            cuenta_limpia = normalizar_cuenta(texto_usuario)
            gasto_pendiente['cuenta'] = cuenta_limpia
            
            guardar_en_sheets(gasto_pendiente)
            del memoria_usuarios[numero] # Borramos de la memoria porque ya terminó
            enviar_whatsapp(numero, f"✅ Listo. ${gasto_pendiente['monto']} en **{cuenta_limpia}**.")
            return # TERMINAMOS AQUÍ. No seguimos al Router.

        # 2. SI NO HAY PENDIENTES, USAMOS EL ROUTER
        intencion = decidir_intencion(texto_usuario)
        print(f"🧠 Intención detectada: {intencion}")

        if intencion == "CONSULTA":
            enviar_whatsapp(numero, "🧐 Déjame revisar tus números...")
            df = obtener_gastos_mes_actual() 
            respuesta = analizar_consultas_ia(texto_usuario, df)
            enviar_whatsapp(numero, respuesta)

        elif intencion == "GASTO":
            respuesta_ia = interpretar_gasto(texto_usuario)
            if respuesta_ia.get("gastos"):
                gasto = respuesta_ia["gastos"][0]
                
                # Caso 1: Falta el monto
                if gasto['monto'] == 0:
                    enviar_whatsapp(numero, f"👂 Escuché: '{texto_usuario}'\n🤷‍♂️ Pero no entendí el monto.")
                
                # Caso 2: Falta la cuenta (AQUÍ ENTRA TU CASO)
                elif not gasto.get('cuenta'):
                    memoria_usuarios[numero] = gasto # Guardamos en memoria
                    enviar_whatsapp(numero, f"🤔 Entendido: {gasto['item']} (${gasto['monto']}).\n\n¿Con qué pagaste?")
                
                # Caso 3: Todo listo
                else:
                    guardar_en_sheets(gasto)
                    enviar_whatsapp(numero, f"✅ Listo! {gasto['item']} (${gasto['monto']}) anotado en {gasto['cuenta']}.")
            else:
                enviar_whatsapp(numero, "👋 No entendí si es un gasto.")
        
        else:
            enviar_whatsapp(numero, "👋 ¡Hola! Soy tu bot de finanzas. Dime un gasto (ej: 'gaste 5 lucas') o hazme una pregunta.")

    except Exception as e:
        print(f"❌ Error lógica: {e}")
        enviar_whatsapp(numero, "😵 Tuve un error interno procesando eso.")

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        if request.args.get("hub.verify_token") == VERIFY_TOKEN:
            return request.args.get("hub.challenge")
        return "Token inválido", 403

    datos = request.get_json()
    try:
        if datos.get("object") == "whatsapp_business_account":
            entrada = datos["entry"][0]["changes"][0]["value"]
            if "messages" in entrada:
                mensaje = entrada["messages"][0]
                msg_id = mensaje["id"]
                if msg_id in mensajes_procesados: return "EVENT_RECEIVED", 200
                mensajes_procesados[msg_id] = True
                
                numero = mensaje["from"]
                tipo = mensaje["type"]
                texto_usuario, audio_id = "", None
                
                if tipo == "text": texto_usuario = mensaje["text"]["body"]
                elif tipo in ["audio", "voice"]: 
                    audio_id = mensaje.get("audio", {}).get("id") or mensaje.get("voice", {}).get("id")
                
                if texto_usuario or audio_id:
                    t = threading.Thread(target=procesar_mensaje_background, args=(numero, texto_usuario, tipo, msg_id, audio_id))
                    t.start()
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
