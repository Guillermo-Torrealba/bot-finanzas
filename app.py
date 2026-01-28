import os
import time
import threading # <--- IMPORTANTE: La herramienta para trabajar en paralelo
from flask import Flask, request
import requests
from cerebro_chatgpt import interpretar_gasto, normalizar_cuenta 
from cerebro_sheets import guardar_en_sheets

app = Flask(__name__)

# --- TUS DATOS ---
TOKEN_WHATSAPP = os.getenv("TOKEN_WHATSAPP")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "un_secreto_cualquiera_123")

# --- MEMORIA VOLÁTIL ---
memoria_usuarios = {} 
mensajes_procesados = {} 

# --- FUNCIÓN QUE PIENSA (SEGUNDO PLANO) ---
def procesar_mensaje_background(numero, texto_usuario, mensaje_id):
    """
    Esta función corre en paralelo para no hacer esperar a Facebook.
    """
    print(f"🔄 Procesando en segundo plano: {texto_usuario}")
    
    try:
        # 1. ¿Es respuesta a una pregunta pendiente?
        if numero in memoria_usuarios:
            gasto_pendiente = memoria_usuarios[numero]
            cuenta_limpia = normalizar_cuenta(texto_usuario)
            gasto_pendiente['cuenta'] = cuenta_limpia
            
            guardar_en_sheets(gasto_pendiente)
            del memoria_usuarios[numero]
            enviar_whatsapp(numero, f"✅ Listo. ${gasto_pendiente['monto']} en **{cuenta_limpia}**.")
        
        # 2. Es un mensaje nuevo
        else:
            respuesta_ia = interpretar_gasto(texto_usuario)
            if respuesta_ia.get("gastos"):
                gasto = respuesta_ia["gastos"][0]
                
                if gasto['monto'] == 0:
                    enviar_whatsapp(numero, "🤷‍♂️ No entendí el monto. Intenta ej: 'Sushi 5000'.")
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
                # Si ya lo tenemos en la lista, abortamos INMEDIATAMENTE
                if msg_id in mensajes_procesados:
                    return "EVENT_RECEIVED", 200
                
                # Marcamos como procesado
                mensajes_procesados[msg_id] = True
                
                # Extraemos datos básicos
                numero = mensaje["from"]
                tipo = mensaje["type"]
                texto_usuario = ""
                
                if tipo == "text":
                    texto_usuario = mensaje["text"]["body"]
                
                if texto_usuario:
                    # --- LANZAMOS EL HILO ---
                    # Esto inicia la función 'procesar_mensaje_background' en paralelo
                    # y permite que el código siga hacia abajo al instante.
                    hilo = threading.Thread(target=procesar_mensaje_background, args=(numero, texto_usuario, msg_id))
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