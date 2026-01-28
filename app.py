import os
from flask import Flask, request
import requests
# AQUI AGREGAMOS "normalizar_cuenta"
from cerebro_chatgpt import interpretar_gasto, normalizar_cuenta 
from cerebro_sheets import guardar_en_sheets

app = Flask(__name__)

TOKEN_WHATSAPP = os.getenv("TOKEN_WHATSAPP")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "un_secreto_cualquiera_123") # Valor por defecto si no encuentra nada

# --- MEMORIA A CORTO PLAZO ---
memoria_usuarios = {} 

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
    try:
        if datos.get("object") == "whatsapp_business_account":
            entrada = datos["entry"][0]["changes"][0]["value"]
            if "messages" in entrada:
                mensaje = entrada["messages"][0]
                numero = mensaje["from"]
                tipo = mensaje["type"]
                
                texto_usuario = ""
                if tipo == "text":
                    texto_usuario = mensaje["text"]["body"]
                
                if texto_usuario:
                    print(f"📩 Mensaje de {numero}: {texto_usuario}")

                    # --- LÓGICA DE CONVERSACIÓN ---
                    
                    # CASO 1: ¿El usuario está respondiendo una pregunta pendiente?
                    if numero in memoria_usuarios:
                        # Recuperamos el gasto que teníamos en pausa
                        gasto_pendiente = memoria_usuarios[numero]
                        
                        # --- NUEVO: Usamos la IA para entender la cuenta ---
                        cuenta_limpia = normalizar_cuenta(texto_usuario)
                        gasto_pendiente['cuenta'] = cuenta_limpia
                        # ---------------------------------------------------
                        
                        # Ahora sí, guardamos todo
                        guardar_en_sheets(gasto_pendiente)
                        
                        # Borramos de la memoria (ya terminamos)
                        del memoria_usuarios[numero]
                        
                        enviar_whatsapp(numero, f"✅ Listo. Gasto de ${gasto_pendiente['monto']} anotado en **{cuenta_limpia}**.")
                    
# CASO 2: Es un mensaje nuevo (Gasto inicial)
                    else:
                        respuesta_ia = interpretar_gasto(texto_usuario)
                        
                        if respuesta_ia.get("gastos"):
                            gasto = respuesta_ia["gastos"][0]

                            # --- 🛑 NUEVO FILTRO ANTI-CERO ---
                            # Si ChatGPT devolvió 0, significa que no entendió nada.
                            # No lo guardamos ni preguntamos nada.
                            if gasto['monto'] == 0:
                                enviar_whatsapp(numero, "🤷‍♂️ No encontré un monto válido. Intenta ej: 'Sushi 5000'.")
                            
                            # Si tiene monto real, seguimos normal...
                            elif not gasto.get('cuenta'):
                                # Guardamos este gasto en la memoria temporal
                                memoria_usuarios[numero] = gasto
                                # Preguntamos al usuario
                                enviar_whatsapp(numero, f"🤔 Entendido: {gasto['item']} por ${gasto['monto']}.\n\nPero dime, **¿con qué medio pagaste?**")
                            
                            else:
                                # Si ya traía cuenta Y monto, guardamos directo
                                guardar_en_sheets(gasto)
                                enviar_whatsapp(numero, f"✅ Listo! {gasto['item']} (${gasto['monto']}) anotado en {gasto['cuenta']}.")
                            # ----------------------------------
                        
                        else:
                            enviar_whatsapp(numero, "👋 Hola! Dime qué compraste.")

        return "OK", 200
    except Exception as e:
        print("Error:", e)
        return "Error", 500

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
    requests.post(url, headers=headers, json=data)

if __name__ == "__main__":
    app.run(port=5000)

