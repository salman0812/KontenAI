import requests
import time
import os
import json
import base64
from io import BytesIO

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
POLLINATIONS_URL = "https://image.pollinations.ai/prompt"

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
Kamu adalah asisten kreatif. Ubah perintah user menjadi daftar adegan detail (2-4 adegan).

Format output HARUS JSON:
{{
  "jumlah": 3,
  "adegan": ["deskripsi detail 1", "deskripsi detail 2", "deskripsi detail 3"]
}}

Input: {user_text}
"""
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
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
    except:
        return 0, []

def generate_frame(reference_image_bytes, adegan_prompt, index):
    print(f"[POLLINATIONS] Generate adegan {index}...")
    
    # Pollinations gak support reference image langsung, jadi kita kirim prompt aja
    full_prompt = f"{adegan_prompt}, cinematic, photorealistic, 8K, natural lighting"
    encoded_prompt = requests.utils.quote(full_prompt)
    
    try:
        response = requests.get(f"{POLLINATIONS_URL}/{encoded_prompt}")
        if response.status_code == 200:
            return response.content
        else:
            return None
    except:
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
    
    if "caption" not in message:
        send_message_to_telegram(chat_id, "Kirim foto + caption prompt.")
        return
    
    caption = message["caption"]
    
    send_message_to_telegram(chat_id, "Memahami permintaan...")
    jumlah, adegan_list = parse_user_prompt(caption)
    
    if jumlah == 0 or not adegan_list:
        send_message_to_telegram(chat_id, "Gagal memahami prompt.")
        return
    
    send_message_to_telegram(chat_id, f"Memproses {jumlah} adegan...")
    
    for i, adegan in enumerate(adegan_list, 1):
        frame_bytes = generate_frame(None, adegan, i)
        if frame_bytes:
            send_image_to_telegram(chat_id, frame_bytes, f"Adegan {i}/{jumlah}")
        else:
            send_message_to_telegram(chat_id, f"Gagal generate adegan {i}.")
    
    send_message_to_telegram(chat_id, f"Selesai. {jumlah} adegan dibuat.")

def main():
    print("[BOT] Bot Pollinations + Groq berjalan...")
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
