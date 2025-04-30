from flask import Flask, request, jsonify
from flask_cors import CORS
from g4f.client import Client
import logging
import requests

app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)
client = Client()

# Tu clave ImgBB
IMGBB_API_KEY = "4bf9cca241b2a50667882775955ab6a7"

# Modelos preferidos en orden
PREFERRED_MODELS = ["flux", "dall-e", "gpt-4o-mini", "midjourney"]

import tempfile

def upload_to_imgbb(image_url):
    try:
        response = requests.get(image_url, stream=True)
        if response.status_code != 200:
            raise Exception("No se pudo descargar la imagen.")

        # Guardamos la imagen en un archivo temporal
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmpfile:
            for chunk in response.iter_content(1024):
                tmpfile.write(chunk)
            tmpfile_path = tmpfile.name

        # Enviar el archivo binario con multipart/form-data
        with open(tmpfile_path, "rb") as f:
            files = {"image": f}
            payload = {"key": IMGBB_API_KEY}
            upload_url = "https://api.imgbb.com/1/upload"
            upload_response = requests.post(upload_url, data=payload, files=files)

        if upload_response.status_code != 200:
            raise Exception(f"Error HTTP {upload_response.status_code}: {upload_response.text}")

        json_data = upload_response.json()

        if not json_data.get("success"):
            raise Exception(f"ImgBB respondió con error: {json_data.get('error', {}).get('message', 'Sin mensaje')}")

        return json_data["data"]["url"]

    except Exception as e:
        logging.error(f"Error al subir a ImgBB: {e}")
        return None

@app.route("/generate-image", methods=["POST"])
def generate_image():
    data = request.get_json()
    prompt = data.get("prompt")

    if not prompt:
        return jsonify({"error": "El campo 'prompt' es obligatorio."}), 400

    # Traducir el prompt a inglés
    try:
        translation_response = requests.post(
            "https://libretranslate.com/translate",
            headers={"Content-Type": "application/json"},
            json={
                "q": prompt,
                "source": "es",
                "target": "en",
                "format": "text",
                "alternatives": 3,
                "api_key": ""
            }
        )
        translation_response.raise_for_status()
        translated_data = translation_response.json()
        translated_prompt = translated_data.get("translatedText")
        
        if not translated_prompt:
            logging.error("No se recibió el texto traducido.")
            return jsonify({"error": "No se pudo traducir el prompt."}), 500
            
    except requests.exceptions.RequestException as e:
        logging.error(f"Error en la API de traducción: {e}")
        return jsonify({"error": "Error al traducir el prompt."}), 500

    logging.info(f"Prompt traducido: {translated_prompt}")

    # Usar el prompt traducido para generar la imagen
    for model in PREFERRED_MODELS:
        try:
            logging.info(f"Intentando con modelo: {model}")
            response = client.images.generate(
                model=model,
                prompt=translated_prompt,
                response_format="url"
            )
            image_url = response.data[0].url

            # Subimos la imagen a ImgBB
            imgbb_url = upload_to_imgbb(image_url)
            if not imgbb_url:
                continue  # Si falla, probamos con otro modelo

            # ✅ ¡Éxito! Devolvemos solo el enlace
            return jsonify({
                "image_url": imgbb_url,
                "original_prompt": prompt,
                "translated_prompt": translated_prompt
            }), 200

        except Exception as e:
            logging.warning(f"Modelo '{model}' falló: {str(e)}")
            continue

    # ❌ Si todos fallan
    return jsonify({"error": "No se pudo generar y/o alojar la imagen."}), 500

@app.route("/")
def index():
    return jsonify({"message": "API de generación de imágenes lista"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)