import os
import time
from flask import Flask, request
import requests
from cerebro_chatgpt import interpretar_gasto, normalizar_cuenta 
from cerebro_sheets import guardar_en_sheets

app = Flask(__name__)

# --- TUS DATOS SEGUROS ---
TOKEN_WHATSAPP = os.getenv("TOKEN_WHATSAPP")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "un_secreto_cualquiera_123")

# --- MEMORIA (RAM) ---
memoria_usuarios = {} 
mensajes_procesados = {} # AQUÍ guardaremos los IDs para no repetir

@app.route("/webhook", methods=["GET"])
def verificar_token():
    token_enviado = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if token_enviado == VERIFY_TOKEN:
        return challenge
    return "Token inválido", 403

@app.route("/webhook", methods=["POST"])
def recibir_mensaje():
    datos = request.get_json()
    
    # Limpieza de memoria (opcional, para que no crezca infinito)
    # Si la lista es muy grande (más de 100 mensajes), la borramos
    if len(mensajes_procesados) > 100:
        mensajes_procesados.clear()

    try:
        if datos.get("object") == "whatsapp_business_account":
            entrada = datos["entry"][0]["changes"][0]["value"]
            
            # FILTRO 1: ¿Es un mensaje real? (Ignoramos estados como "leído", "enviado")
            if "messages" in entrada:
                mensaje = entrada["messages"][0]
                
                # FILTRO 2: DETECTOR DE DUPLICADOS
                msg_id = mensaje["id"] # El ID único de WhatsApp
                if msg_id in mensajes_procesados:
                    print(f"🛑 Mensaje duplicado detectado ({msg_id}). Ignorando.")
                    return "OK", 200 # Le decimos a Facebook "Ya lo tengo, cállate"
                
                # Si es nuevo, lo agregamos a la lista de procesados
                mensajes_procesados[msg_id] = True
                
                # --- AHORA SÍ PROCESAMOS ---
                numero = mensaje["from"]
                tipo = mensaje["type"]
                texto_usuario = ""
                
                if tipo == "text":
                    texto_usuario = mensaje["text"]["body"]
                elif tipo == "audio":
                    # (Aquí pondremos lo del audio más adelante)
                    texto_usuario = ""

                if texto_usuario:
                    print(f"📩 Mensaje nuevo de {numero}: {texto_usuario}")

                    # --- LÓGICA DE CONVERSACIÓN ---
                    if numero in memoria_usuarios:
                        gasto_pendiente = memoria_usuarios[numero]
                        cuenta_limpia = normalizar_cuenta(texto_usuario)
                        gasto_pendiente['cuenta'] = cuenta_limpia
                        
                        guardar_en_sheets(gasto_pendiente)
                        del memoria_usuarios[numero]
                        enviar_whatsapp(numero, f"✅ Listo. ${gasto_pendiente['monto']} en **{cuenta_limpia}**.")
                    
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
                                enviar_whatsapp(numero, f"✅ Listo! {gasto['item']} (${gasto['monto']}) en {gasto['cuenta']}.")
                        else:
                            enviar_whatsapp(numero, "👋 Hola! Dime qué compraste.")

        return "OK", 200
    except Exception as e:
        print("Error:", e)
        # IMPORTANTE: Respondemos 200 aunque falle, para que Facebook no reintente
        return "Error", 200 

def enviar_whatsapp(numero, texto):
    url = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {TOKEN_WHATSAPP}",
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "text",
        "text": {"body": texto}
    }
    try:
        requests.post(url, headers=headers, json=data, timeout=10)
    except Exception as e:
        print(f"Error enviando WhatsApp: {e}")

if __name__ == "__main__":
    app.run(port=5000)

