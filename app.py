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


def translate_prompt(prompt_sp):
    """Traduce el prompt del español al inglés usando g4f."""
    translation_prompt = (
        "You are an assistant specialized in translating Spanish to English. "
        "Please translate the following text into a clear and accurate English version, "
        "ensuring it maintains its original intent and meaning for optimal use in image generation.\n\n"
        f"{prompt_sp}"
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Puedes cambiar por otro disponible en g4f
            messages=[{"role": "user", "content": translation_prompt}],
        )
        translated_text = response.choices[0].message.content.strip()
        logging.info(f"Prompt traducido: {translated_text}")
        return translated_text
    except Exception as e:
        logging.error(f"Error al traducir: {e}")
        return prompt_sp  # Fallback: usar el original si falla


@app.route("/generate-image", methods=["POST"])
def generate_image():
    data = request.get_json()
    prompt_sp = data.get("prompt")

    if not prompt_sp:
        return jsonify({"error": "El campo 'prompt' es obligatorio."}), 400

    # Traducir el prompt
    prompt_en = translate_prompt(prompt_sp)

    # Intentar generar imagen con cada modelo
    for model in PREFERRED_MODELS:
        try:
            logging.info(f"Intentando con modelo: {model}")
            response = client.images.generate(
                model=model,
                prompt=prompt_en,
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
                "translated_prompt": prompt_en
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