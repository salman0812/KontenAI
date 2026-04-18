import requests
import time
import os
import json
import base64

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
HF_API_KEY = os.environ.get("HF_API_KEY")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
HF_URL = "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent?key={GEMINI_API_KEY}"

QUALITY_SUFFIX = (
    "ultra photorealistic, hyperrealistic, natural lighting, sharp focus, "
    "8k uhd, high resolution, masterpiece, cinematic, "
    "professional photography, raw photo, detailed texture, "
    "realistic shadows, depth of field"
)

NEGATIVE = (
    "cartoon, anime, painting, illustration, blurry, low quality, "
    "deformed, ugly, unrealistic, fake, CGI, plastic skin"
)

# Simpan state user: mode & history
user_state = {}

def send_message(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    requests.post(url, json=data)

def send_image(chat_id, image_bytes, caption=""):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    files = {"photo": ("frame.jpg", image_bytes, "image/jpeg")}
    data = {"chat_id": chat_id, "caption": caption}
    requests.post(url, files=files, data=data)

def answer_callback(callback_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
    requests.post(url, data={"callback_query_id": callback_id})

def download_image(file_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile"
    response = requests.post(url, data={"file_id": file_id})
    if response.status_code != 200:
        return None
    file_path = response.json()["result"]["file_path"]
    file_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
    return requests.get(file_url).content

def main_menu():
    return {
        "inline_keyboard": [[
            {"text": "🎬 Generate Frame", "callback_data": "mode_generate"},
            {"text": "✍️ Prompt Video", "callback_data": "mode_prompt"}
        ]]
    }

def parse_adegan(user_text):
    prompt = f"""
Ubah perintah user menjadi daftar adegan sinematik detail (2-4 adegan).
Format output HARUS JSON:
{{"jumlah": 3, "adegan": ["deskripsi 1", "deskripsi 2", "deskripsi 3"]}}
Tulis setiap adegan dalam bahasa Inggris, deskriptif: subjek, aksi, latar, pencahayaan, suasana.
Input: {user_text}
"""
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    data = {"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt}], "temperature": 0.7, "response_format": {"type": "json_object"}}
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
            "num_inference_steps": 4,
            "width": 1024,
            "height": 1024
        }
    }
    for attempt in range(3):
        try:
            response = requests.post(HF_URL, headers=headers, json=data, timeout=120)
            print(f"[HF] Status: {response.status_code}", flush=True)
            if response.status_code == 200:
                return response.content
            elif response.status_code == 503:
                wait = response.json().get("estimated_time", 20)
                print(f"[HF] Loading {wait}s...", flush=True)
                time.sleep(wait)
            else:
                print(f"[HF] Error: {response.text[:300]}", flush=True)
                return None
        except Exception as e:
            print(f"[HF] Exception: {e}", flush=True)
            time.sleep(5)
    return None

def gemini_buat_prompt(images_b64, instruksi, history):
    print("[GEMINI] Buat prompt video...", flush=True)

    parts = []
    for img in images_b64:
        parts.append({"inlineData": {"mimeType": "image/jpeg", "data": img}})
    parts.append({"text": instruksi})

    messages = []
    for h in history:
        messages.append(h)
    messages.append({"role": "user", "parts": parts})

    system = """Kamu adalah ahli prompt video AI (Pika, Kling, Runway, Hailuo, dll).
Tugasmu: analisis gambar yang dikirim user, lalu buat prompt video yang sangat detail dan optimal.
Sertakan: deskripsi scene, gerakan kamera, aksi karakter, suasana, pencahayaan, dan timestamp jika diminta.
Jika user minta revisi, perbaiki sesuai feedback. Gunakan bahasa yang diminta user (Indonesia/Inggris)."""

    data = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": messages,
        "generationConfig": {"temperature": 0.8, "maxOutputTokens": 2048}
    }

    try:
        response = requests.post(GEMINI_URL, json=data)
        result = response.json()
        print(f"[GEMINI] Status: {response.status_code}", flush=True)
        text = result["candidates"][0]["content"]["parts"][0]["text"]
        return text, messages + [{"role": "model", "parts": [{"text": text}]}]
    except Exception as e:
        print(f"[GEMINI] Error: {e}", flush=True)
        print(f"[GEMINI] Raw: {response.text[:300]}", flush=True)
        return None, history

def process_message(update):
    if "message" not in update:
        return
    message = update["message"]
    chat_id = message["chat"]["id"]
    state = user_state.get(chat_id, {"mode": None, "history": [], "images": []})

    # Handle /start
    if message.get("text") == "/start":
        user_state[chat_id] = {"mode": None, "history": [], "images": []}
        send_message(chat_id, "👋 Halo! Pilih mode:", reply_markup=main_menu())
        return

    mode = state.get("mode")

    # Mode Generate Frame
    if mode == "generate":
        text = message.get("caption") or message.get("text")
        if not text:
            send_message(chat_id, "Kirim teks prompt atau foto + caption.")
            return
        send_message(chat_id, "⏳ Memahami permintaan...")
        jumlah, adegan_list = parse_adegan(text)
        if jumlah == 0:
            send_message(chat_id, "❌ Gagal memahami prompt.")
            return
        send_message(chat_id, f"🎬 Generating {jumlah} frame HD...")
        for i, adegan in enumerate(adegan_list, 1):
            frame = generate_frame(adegan, i)
            if frame:
                send_image(chat_id, frame, f"Frame {i}/{jumlah}")
            else:
                send_message(chat_id, f"❌ Gagal generate frame {i}.")
        send_message(chat_id, f"✅ Selesai! {jumlah} frame dibuat.", reply_markup=main_menu())
        user_state[chat_id] = {"mode": None, "history": [], "images": []}

    # Mode Prompt Video
    elif mode == "prompt":
        images_b64 = state.get("images", [])

        # Kalau ada foto, simpan
        if "photo" in message:
            photo = message["photo"][-1]
            img_bytes = download_image(photo["file_id"])
            if img_bytes:
                images_b64.append(base64.b64encode(img_bytes).decode('utf-8'))
                state["images"] = images_b64
                user_state[chat_id] = state

        text = message.get("caption") or message.get("text")
        if not text:
            send_message(chat_id, f"📸 Foto tersimpan ({len(images_b64)} foto). Kirim instruksi atau foto lagi.")
            return

        if not images_b64:
            send_message(chat_id, "Kirim foto dulu sebelum instruksi.")
            return

        send_message(chat_id, "🤖 Gemini sedang membuat prompt video...")
        result, new_history = gemini_buat_prompt(images_b64, text, state.get("history", []))

        if result:
            send_message(chat_id, f"📝 *Prompt Video:*\n\n{result}")
            send_message(chat_id, "Mau direvisi? Ketik instruksi perbaikan, atau pilih mode lain.", reply_markup=main_menu())
            state["history"] = new_history
            state["mode"] = "prompt_revisi"
            user_state[chat_id] = state
        else:
            send_message(chat_id, "❌ Gagal generate prompt.", reply_markup=main_menu())

    # Mode Revisi Prompt
    elif mode == "prompt_revisi":
        text = message.get("text")
        if not text:
            return
        send_message(chat_id, "🔄 Merevisi prompt...")
        result, new_history = gemini_buat_prompt(state.get("images", []), text, state.get("history", []))
        if result:
            send_message(chat_id, f"📝 *Prompt Video (Revisi):*\n\n{result}")
            send_message(chat_id, "Mau direvisi lagi? Atau pilih mode lain.", reply_markup=main_menu())
            state["history"] = new_history
            user_state[chat_id] = state
        else:
            send_message(chat_id, "❌ Gagal revisi.", reply_markup=main_menu())

    else:
        send_message(chat_id, "Pilih mode dulu:", reply_markup=main_menu())

def process_callback(update):
    if "callback_query" not in update:
        return
    cb = update["callback_query"]
    chat_id = cb["message"]["chat"]["id"]
    data = cb["data"]
    answer_callback(cb["id"])

    if data == "mode_generate":
        user_state[chat_id] = {"mode": "generate", "history": [], "images": []}
        send_message(chat_id, "🎬 *Mode Generate Frame*\nKirim teks prompt atau foto + caption.")
    elif data == "mode_prompt":
        user_state[chat_id] = {"mode": "prompt", "history": [], "images": []}
        send_message(chat_id, "✍️ *Mode Prompt Video*\nKirim foto-foto frame + instruksi (platform, kegiatan, timestamp, dll).")

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
                    if "callback_query" in update:
                        process_callback(update)
                    else:
                        process_message(update)
            time.sleep(1)
        except Exception as e:
            print(f"[BOT] Error: {e}", flush=True)
            time.sleep(5)

if __name__ == "__main__":
    main()
