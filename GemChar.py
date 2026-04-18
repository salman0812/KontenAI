import requests
import time
import os
import json
import base64
from io import BytesIO
import traceback

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

GEMINI_IMAGE_URL = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash-image:generateContent?key={GEMINI_API_KEY}"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

def download_telegram_image(file_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile"
    response = requests.post(url, data={"file_id": file_id})
    if response.status_code != 200:
        return None
    file_path = response.json()["result"]["file_path"]
    file_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
    return requests.get(file_url).content

def parse_user_prompt(user_text):
    prompt_groq = f"""
Kamu adalah asisten kreatif. User memberikan perintah bebas tentang adegan yang diinginkan.

Tugasmu: Ubah perintah user menjadi daftar adegan detail. Tentukan sendiri jumlah adegan yang pas (antara 2-6 adegan).

Format output HARUS JSON valid:
{{
  "jumlah": 3,
  "adegan": [
    "deskripsi detail adegan 1",
    "deskripsi detail adegan 2",
    "deskripsi detail adegan 3"
  ]
}}

Input user: {user_text}
"""
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt_groq}],
        "temperature": 0.7,
        "response_format": {"type": "json_object"}
    }
    
    try:
        response = requests.post(GROQ_URL, headers=headers, json=data)
        result = response.json()
        content = result["choices"][0]["message"]["content"]
        hasil = json.loads(content)
        return hasil.get("jumlah", 0), hasil.get("adegan", [])
    except Exception as e:
        print(f"[GROQ] Error: {e}")
        traceback.print_exc()
        return 0, []

def generate_frame(reference_image_bytes, adegan_prompt, index):
    print(f"[GEMINI] Generate adegan {index}...")
    
    image_base64 = base64.b64encode(reference_image_bytes).decode('utf-8')
    
    full_prompt = f"""
Generate an image based on this reference photo. Keep the character's face, skin tone, body shape, and clothing EXACTLY the same as the reference. Only change the background, pose, and expression.

Scene: {adegan_prompt}
Style: Cinematic, photorealistic, natural lighting.
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
        print(f"[GEMINI] Response status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"[GEMINI] Error response: {response.text}")
            return None
        
        result = response.json()
        print(f"[GEMINI] Result keys: {result.keys()}")
        
        if "candidates" not in result:
            print(f"[GEMINI] No candidates in response: {result}")
            return None
            
        image_data = result["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
        return base64.b64decode(image_data)
        
    except Exception as e:
        print(f"[GEMINI] Exception: {e}")
        traceback.print_exc()
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
        send_message_to_telegram(chat_id, "Gagal memahami prompt. Coba tulis ulang.")
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
    print("[BOT] Bot Gemini + Groq berjalan...")
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
            traceback.print_exc()
            time.sleep(5)

if __name__ == "__main__":
    main()
