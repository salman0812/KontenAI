import requests
import time
import os
import json

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
HF_API_KEY = os.environ.get("HF_API_KEY")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
HF_URL = "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-dev"

QUALITY_SUFFIX = (
    "ultra photorealistic, hyperrealistic, natural lighting, sharp focus, "
    "8k uhd, high resolution, masterpiece, perfect anatomy, cinematic, "
    "professional photography, raw photo, detailed skin texture, "
    "realistic shadows, depth of field"
)

NEGATIVE = (
    "cartoon, anime, painting, illustration, blurry, low quality, "
    "deformed, ugly, unrealistic, fake, CGI, plastic skin"
)

def parse_user_prompt(user_text):
    prompt_groq = f"""
Kamu adalah asisten kreatif konten visual. Ubah perintah user menjadi daftar adegan sinematik detail (2-4 adegan).
Format output HARUS JSON:
{{"jumlah": 3, "adegan": ["deskripsi 1", "deskripsi 2", "deskripsi 3"]}}
Tulis setiap adegan dalam bahasa Inggris, sangat deskriptif: subjek, aksi, latar, pencahayaan, suasana.
Jangan deskripsikan kualitas gambar, itu sudah dihandle otomatis.
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
        hasil = json.loads(response.json()["choices"][0]["message"]["content"])
        return hasil.get("jumlah", 0), hasil.get("adegan", [])
    except Exception as e:
        print(f"[GROQ] Error: {e}", flush=True)
        return 0, []

def generate_frame(adegan_prompt, index):
    print(f"[HF] Generate adegan {index}...", flush=True)

    full_prompt = f"{adegan_prompt}, {QUALITY_SUFFIX}"

    headers = {"Authorization": f"Bearer {HF_API_KEY}"}
    data = {
        "inputs": full_prompt,
        "parameters": {
            "negative_prompt": NEGATIVE,
            "num_inference_steps": 50,
            "guidance_scale": 7.5,
            "width": 1024,
            "height": 1024
        }
    }

    for attempt in range(3):
        try:
            response = requests.post(HF_URL, headers=headers, json=data, timeout=120)
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

    text = message.get("caption") or message.get("text")
    if not text:
        send_message_to_telegram(chat_id, "Kirim prompt teks atau foto + caption.")
        return

    print(f"[BOT] Pesan dari {chat_id}: {text}", flush=True)

    send_message_to_telegram(chat_id, "⏳ Memahami permintaan...")
    jumlah, adegan_list = parse_user_prompt(text)

    if jumlah == 0 or not adegan_list:
        send_message_to_telegram(chat_id, "Gagal memahami prompt.")
        return

    send_message_to_telegram(chat_id, f"🎬 Generating {jumlah} frame HD...")

    for i, adegan in enumerate(adegan_list, 1):
        frame_bytes = generate_frame(adegan, i)
        if frame_bytes:
            send_image_to_telegram(chat_id, frame_bytes, f"Frame {i}/{jumlah}")
        else:
            send_message_to_telegram(chat_id, f"Gagal generate frame {i}.")

    send_message_to_telegram(chat_id, f"✅ Selesai. {jumlah} frame dibuat.")

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
