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


def translate_prompt_to_english(prompt):
    """Usa G4F para traducir el prompt al inglés."""
    try:
        logging.info(f"Traduciendo prompt al inglés: {prompt}")
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Traduce el siguiente texto al inglés contextualmente. Solo devuelve la traducción sin comentarios adicionales."},
                {"role": "user", "content": prompt}
            ]
        )
        translated_text = response.choices[0].message.content.strip()
        logging.info(f"Prompt traducido: {translated_text}")
        return translated_text
    except Exception as e:
        logging.error(f"No se pudo traducir el prompt: {str(e)}")
        return prompt  # Devolver original como fallback


@app.route("/generate-image", methods=["POST"])
def generate_image():
    data = request.get_json()
    prompt = data.get("prompt")
    requested_model = data.get("model")         # Modelo opcional
    translate_flag = data.get("translate_to_en", False)  # Por defecto no traduce

    if not prompt:
        return jsonify({"error": "El campo 'prompt' es obligatorio."}), 400

    logging.info(f"Recibida solicitud - Prompt: {prompt}, Traducir: {translate_flag}, Modelo: {requested_model}")

    # Traducimos si así se indica
    final_prompt = translate_prompt_to_english(prompt) if translate_flag else prompt
    logging.info(f"Prompt final a usar: {final_prompt}")

    # Si se especificó un modelo, usamos solo ese
    if requested_model:
        try:
            logging.info(f"Generando imagen con modelo solicitado: {requested_model}")
            response = client.images.generate(
                model=requested_model,
                prompt=final_prompt,
                response_format="url"
            )
            image_url = response.data[0].url

            imgbb_url = upload_to_imgbb(image_url)
            if not imgbb_url:
                return jsonify({"error": "No se pudo alojar la imagen generada."}), 500

            return jsonify({
                "image_url": imgbb_url,
                "model_used": requested_model,
                "original_prompt": prompt,
                "final_prompt": final_prompt,
                "was_translated": translate_flag
            }), 200

        except Exception as e:
            logging.error(f"Modelo '{requested_model}' falló: {str(e)}")
            return jsonify({"error": f"No se pudo generar la imagen con el modelo '{requested_model}': {str(e)}"}), 500

    # Si no se especificó modelo, probamos con los por defecto
    for model in PREFERRED_MODELS:
        try:
            logging.info(f"Intentando con modelo: {model}")
            response = client.images.generate(
                model=model,
                prompt=final_prompt,
                response_format="url"
            )
            image_url = response.data[0].url

            imgbb_url = upload_to_imgbb(image_url)
            if not imgbb_url:
                continue  # Si falla, probamos con otro modelo

            # ✅ ¡Éxito! Devolvemos imagen, modelo usado y traducción del prompt
            return jsonify({
                "image_url": imgbb_url,
                "model_used": model,
                "original_prompt": prompt,
                "final_prompt": final_prompt,
                "was_translated": translate_flag
            }), 200

        except Exception as e:
            logging.warning(f"Modelo '{model}' falló: {str(e)}")
            continue

    # ❌ Si todos fallan
    return jsonify({"error": "No se pudo generar y/o alojar la imagen con ningún modelo disponible."}), 500


@app.route("/")
def index():
    return jsonify({"message": "API de generación de imágenes lista"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)