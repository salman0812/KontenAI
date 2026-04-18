import requests
import time
import os
import json
import base64
from io import BytesIO

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Endpoint Gemini untuk generate gambar
GEMINI_IMAGE_URL = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash-image:generateContent?key={GEMINI_API_KEY}"

# Endpoint Gemini Text buat parse prompt
GEMINI_TEXT_URL = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"

def download_telegram_image(file_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile"
    response = requests.post(url, data={"file_id": file_id})
    if response.status_code != 200:
        return None
    file_path = response.json()["result"]["file_path"]
    file_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
    return requests.get(file_url).content

def parse_user_prompt(user_text):
    prompt_parser = f"""
Kamu adalah asisten sutradara AI. User akan memberikan perintah bebas tentang adegan yang diinginkan.

Tugasmu:
1. Tentukan berapa jumlah adegan yang diminta user (angka).
2. Buat deskripsi detail untuk SETIAP adegan.

Format output HARUS JSON:
{{
  "jumlah": 4,
  "adegan": ["deskripsi adegan 1", "deskripsi adegan 2", ...]
}}

Input user: {user_text}
"""
    headers = {"Content-Type": "application/json"}
    data = {
        "contents": [{"parts": [{"text": prompt_parser}]}]
    }
    
    try:
        response = requests.post(GEMINI_TEXT_URL, headers=headers, json=data)
        result = response.json()
        text_response = result["candidates"][0]["content"]["parts"][0]["text"]
        text_response = text_response.replace("```json", "").replace("```", "").strip()
        hasil = json.loads(text_response)
        return hasil.get("jumlah", 0), hasil.get("adegan", [])
    except:
        return 0, []

def generate_frame(reference_image_bytes, adegan_prompt, index):
    print(f"[GEMINI] Generate adegan {index}...")
    
    # Convert gambar ke base64
    image_base64 = base64.b64encode(reference_image_bytes).decode('utf-8')
    
    full_prompt = f"""
[REFERENCE IMAGE PROVIDED]
Foto yang diunggah adalah REFERENSI MUTLAK untuk karakter.
WAJAH, WARNA KULIT, BENTUK TUBUH, DAN PAKAIAN HARUS TETAP SAMA PERSIS.
JANGAN UBAH IDENTITAS KARAKTER. HANYA LATAR BELAKANG, POSE, DAN EKSPRESI YANG BOLEH BERUBAH.

Adegan: {adegan_prompt}
Gaya: Sinematik, fotorealistik, pencahayaan alami.
"""
    
    headers = {"Content-Type": "application/json"}
    data = {
        "contents": [{
            "parts": [
                {"text": full_prompt},
                {"inlineData": {"mimeType": "image/jpeg", "data": image_base64}}
            ]
        }],
        "generationConfig": {
            "responseModalities": ["IMAGE"]
        }
    }
    
    try:
        response = requests.post(GEMINI_IMAGE_URL, headers=headers, json=data)
        result = response.json()
        
        # Extract base64 image dari response
        image_data = result["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
        return base64.b64decode(image_data)
    except Exception as e:
        print(f"[GEMINI] Error: {e}")
        return None

def send_image_to_telegram(chat_id, image_bytes, caption=""):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    files = {"photo": ("frame.jpg", image_bytes, "image/jpeg")}
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
        send_message_to_telegram(chat_id, "Silakan kirim FOTO karakter + prompt bebas.")
        return
    
    if "caption" not in message:
        send_message_to_telegram(chat_id, "Tulis prompt di caption foto.")
        return
    
    photo = message["photo"][-1]
    file_id = photo["file_id"]
    caption = message["caption"]
    
    send_message_to_telegram(chat_id, "Memahami permintaan...")
    jumlah, adegan_list = parse_user_prompt(caption)
    
    if jumlah == 0 or not adegan_list:
        send_message_to_telegram(chat_id, "Gagal memahami prompt.")
        return
    
    send_message_to_telegram(chat_id, f"Memproses {jumlah} adegan...")
    
    reference_image = download_telegram_image(file_id)
    if not reference_image:
        send_message_to_telegram(chat_id, "Gagal download gambar.")
        return
    
    for i, adegan in enumerate(adegan_list, 1):
        frame_bytes = generate_frame(reference_image, adegan, i)
        if frame_bytes:
            send_image_to_telegram(chat_id, frame_bytes, f"Adegan {i}/{jumlah}")
        else:
            send_message_to_telegram(chat_id, f"Gagal generate adegan {i}.")
    
    send_message_to_telegram(chat_id, f"Selesai. {jumlah} adegan dibuat.")

def main():
    print("[BOT] Bot Gemini berjalan...")
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
