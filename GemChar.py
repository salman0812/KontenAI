import requests
import time
import os
import json
import base64

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
HF_API_KEY = os.environ.get("HF_API_KEY")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
HF_URL = "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell"

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
{{"jumlah": 3, "adegan": ["deskripsi 1", "deskripsi 2", "deskripsi 3"]}}
Input: {user_text}
"""
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    data = {"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt_groq}], "temperature": 0.7, "response_format": {"type": "json_object"}}
    try:
        response = requests.post(GROQ_URL, headers=headers, json=data)
        hasil = json.loads(response.json()["choices"][0]["message"]["content"])
        return hasil.get("jumlah", 0), hasil.get("adegan", [])
    except Exception as e:
        print(f"[GROQ] Error: {e}", flush=True)
        return 0, []

def generate_frame(adegan_prompt, index):
    print(f"[HF] Generate adegan {index}...", flush=True)

    full_prompt = f"cinematic photorealistic, natural lighting, Indonesian man cooking rendang beef, {adegan_prompt}, high quality, 4k"

    headers = {"Authorization": f"Bearer {HF_API_KEY}"}
    data = {"inputs": full_prompt}

    for attempt in range(3):
        try:
            response = requests.post(HF_URL, headers=headers, json=data, timeout=60)
            print(f"[HF] Status: {response.status_code}", flush=True)

            if response.status_code == 200:
                print(f"[HF] Adegan {index} berhasil!", flush=True)
                return response.content
            elif response.status_code == 503:
                wait = response.json().get("estimated_time", 20)
                print(f"[HF] Model loading, tunggu {wait}s...", flush=True)
                time.sleep(wait)
            else:
                print(f"[HF] Error: {response.text[:300]}", flush=True)
                return None
        except Exception as e:
            print(f"[HF] Exception: {e}", flush=True)
            time.sleep(5)

    return None

def send_image_to_telegram(chat_id, image_bytes, caption=""):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    files = {"photo": ("frame.jpg", image_bytes, "image/jpeg")}
    data = {"chat_id": chat_id, "caption": caption}
    requests.post(url, files=files, data=data)

def send_message_to_telegram(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": chat_id, "text": text})

def process_telegram_update(update):
    if "message" not in update:
        return
    message = update["message"]
    chat_id = message["chat"]["id"]

    if "photo" not in message or "caption" not in message:
        send_message_to_telegram(chat_id, "Kirim FOTO + caption prompt.")
        return

    photo = message["photo"][-1]
    file_id = photo["file_id"]
    caption = message["caption"]

    print(f"[BOT] Pesan dari {chat_id}: {caption}", flush=True)
    send_message_to_telegram(chat_id, "Memahami permintaan...")
    jumlah, adegan_list = parse_user_prompt(caption)

    if jumlah == 0 or not adegan_list:
        send_message_to_telegram(chat_id, "Gagal memahami prompt.")
        return

    send_message_to_telegram(chat_id, f"Memproses {jumlah} adegan...")

    for i, adegan in enumerate(adegan_list, 1):
        frame_bytes = generate_frame(adegan, i)
        if frame_bytes:
            send_image_to_telegram(chat_id, frame_bytes, f"Adegan {i}/{jumlah}")
        else:
            send_message_to_telegram(chat_id, f"Gagal generate adegan {i}.")

    send_message_to_telegram(chat_id, f"Selesai. {jumlah} adegan dibuat.")

def main():
    print("[BOT] Berjalan...", flush=True)
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
            print(f"[BOT] Error: {e}", flush=True)
            time.sleep(5)

if __name__ == "__main__":
    main()
