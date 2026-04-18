import requests
import time
import os
import base64
from io import BytesIO
from google import genai
from google.genai import types

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

client = genai.Client(api_key=GEMINI_API_KEY)

def download_telegram_image(file_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile"
    response = requests.post(url, data={"file_id": file_id})
    if response.status_code != 200:
        return None
    file_path = response.json()["result"]["file_path"]
    file_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
    return requests.get(file_url).content

def parse_adegan_prompt(user_text):
    if "### FRAME PROMPT ###" not in user_text:
        return None
    parts = user_text.split("### FRAME PROMPT ###")
    if len(parts) < 2:
        return None
    frame_part = parts[1].strip()
    adegan_list = [line.strip() for line in frame_part.split('\n') if line.strip()]
    return adegan_list[:4]

def generate_frame(reference_image_data, adegan_prompt, index):
    print(f"[GEMINI] Generate adegan {index}...")
    
    full_prompt = f"""
[REFERENCE IMAGE PROVIDED]
Gunakan foto yang diunggah sebagai referensi UTAMA untuk WAJAH dan IDENTITAS karakter.
JAGA KONSISTENSI: Wajah, warna kulit, dan pakaian HARUS TETAP SAMA PERSIS.
HANYA LATAR BELAKANG dan POSISI TUBUH yang boleh berubah.

Adegan: {adegan_prompt}
Gaya: Sinematik, fotorealistik, pencahayaan alami, 8K.
"""
    
    try:
        response = client.models.generate_content(
            model="gemini-3-pro-image-preview",
            contents=[full_prompt, types.Part.from_bytes(data=reference_image_data, mime_type="image/jpeg")],
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
                image_config=types.ImageConfig(
                    aspect_ratio="9:16",
                    image_size="1K"
                )
            )
        )
        
        for part in response.candidates[0].content.parts:
            if part.inline_data is not None:
                return part.inline_data.data
        
        return None
    except Exception as e:
        print(f"[GEMINI] Error adegan {index}: {e}")
        return None

def send_image_to_telegram(chat_id, image_data, caption=""):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    files = {"photo": ("frame.jpg", image_data, "image/jpeg")}
    data = {"chat_id": chat_id, "caption": caption}
    requests.post(url, files=files, data=data)

def send_message_to_telegram(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text}
    requests.post(url, data=data)

def process_telegram_update(update):
    if "message" not in update:
        return
    message = update["message"]
    chat_id = message["chat"]["id"]
    if "photo" not in message:
        send_message_to_telegram(chat_id, "Silakan kirim FOTO karakter + prompt 4 adegan.")
        return
    if "caption" not in message:
        send_message_to_telegram(chat_id, "Silakan tulis prompt 4 adegan di caption foto.")
        return
    photo = message["photo"][-1]
    file_id = photo["file_id"]
    caption = message["caption"]
    adegan_list = parse_adegan_prompt(caption)
    if not adegan_list or len(adegan_list) == 0:
        send_message_to_telegram(chat_id, "Format prompt salah. Gunakan:\n### FRAME PROMPT ###\nAdegan 1\nAdegan 2\nAdegan 3\nAdegan 4")
        return
    send_message_to_telegram(chat_id, f"Memproses {len(adegan_list)} adegan... Mohon tunggu 1-2 menit.")
    reference_image = download_telegram_image(file_id)
    if not reference_image:
        send_message_to_telegram(chat_id, "Gagal download gambar.")
        return
    for i, adegan in enumerate(adegan_list, 1):
        frame_image = generate_frame(reference_image, adegan, i)
        if frame_image:
            send_image_to_telegram(chat_id, frame_image, f"Adegan {i}: {adegan}")
        else:
            send_message_to_telegram(chat_id, f"Gagal generate adegan {i}.")
    send_message_to_telegram(chat_id, "Semua adegan selesai diproses.")

def main():
    print("[BOT] Bot Gemini Karakter berjalan...")
    last_update_id = 0
    while True:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
        params = {"offset": last_update_id + 1, "timeout": 30}
        try:
            response = requests.get(url, params=params)
            if response.status_code == 200:
                updates = response.json()["result"]
                for update in updates:
                    last_update_id = update["update_id"]
                    process_telegram_update(update)
            time.sleep(1)
        except Exception as e:
            print(f"[BOT] Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
