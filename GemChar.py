import requests
import time
import os
from io import BytesIO
import google.generativeai as genai
import json

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)

text_model = genai.GenerativeModel("gemini-2.0-flash")
image_model = genai.ImageGenerationModel("models/gemini-3-pro-image-preview")

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
2. Buat deskripsi detail untuk SETIAP adegan. Setiap adegan HARUS mencakup:
   - Aktivitas yang dilakukan karakter.
   - Ekspresi wajah.
   - Latar belakang.
   - Angle kamera (opsional).

Format output HARUS JSON seperti ini:
{{
  "jumlah": 4,
  "adegan": [
    "Mencuci beras di sungai jernih, ekspresi fokus, kamera close-up tangan dan anyaman bambu, latar hutan tropis.",
    "Menyalakan api tungku kayu, ekspresi hati-hati, kamera medium shot, latar dapur tradisional bambu.",
    "Memasukkan beras ke dandang dan menutupnya, ekspresi telaten, kamera side angle.",
    "Mengaduk nasi matang dengan centong kayu, uap mengepul, ekspresi puas, kamera slow motion."
  ]
}}

Input user: {user_text}
"""
    try:
        response = text_model.generate_content(prompt_parser)
        hasil = json.loads(response.text.strip().replace("```json", "").replace("```", ""))
        return hasil.get("jumlah", 0), hasil.get("adegan", [])
    except:
        return 0, []

def generate_frame(reference_image_data, adegan_prompt, index):
    print(f"[GEMINI] Generate adegan {index}...")
    full_prompt = f"""
[REFERENCE IMAGE PROVIDED]
Foto yang diunggah adalah REFERENSI MUTLAK untuk karakter.
WAJAH, WARNA KULIT, BENTUK TUBUH, DAN PAKAIAN HARUS TETAP SAMA PERSIS di setiap adegan.
JANGAN UBAH IDENTITAS KARAKTER. HANYA LATAR BELAKANG, POSE, DAN EKSPRESI YANG BOLEH BERUBAH.

Adegan: {adegan_prompt}
Gaya: Sinematik, fotorealistik, pencahayaan alami, 8K.
"""
    try:
        response = image_model.generate_images(
            prompt=full_prompt,
            reference_images=[reference_image_data],
            number_of_images=1
        )
        return response.images[0]
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
        send_message_to_telegram(chat_id, "Silakan kirim FOTO karakter + prompt bebas (contoh: 'Buat 4 adegan memasak nasi tradisional').")
        return
    
    if "caption" not in message:
        send_message_to_telegram(chat_id, "Tulis prompt di caption foto. Contoh: 'Buat 5 adegan mancing di sungai'.")
        return
    
    photo = message["photo"][-1]
    file_id = photo["file_id"]
    caption = message["caption"]
    
    send_message_to_telegram(chat_id, "Memahami permintaan...")
    jumlah, adegan_list = parse_user_prompt(caption)
    
    if jumlah == 0 or not adegan_list:
        send_message_to_telegram(chat_id, "Gagal memahami prompt. Coba tulis ulang dengan lebih jelas.")
        return
    
    send_message_to_telegram(chat_id, f"Memproses {jumlah} adegan... Mohon tunggu 1-2 menit per adegan.")
    
    reference_image = download_telegram_image(file_id)
    if not reference_image:
        send_message_to_telegram(chat_id, "Gagal download gambar.")
        return
    
    for i, adegan in enumerate(adegan_list, 1):
        frame_image = generate_frame(reference_image, adegan, i)
        if frame_image:
            img_bytes = BytesIO()
            frame_image.save(img_bytes, format="JPEG")
            img_bytes.seek(0)
            send_image_to_telegram(chat_id, img_bytes.getvalue(), f"Adegan {i}/{jumlah}: {adegan}")
        else:
            send_message_to_telegram(chat_id, f"Gagal generate adegan {i}.")
    
    send_message_to_telegram(chat_id, f"Selesai. {jumlah} adegan berhasil dibuat.")

def main():
    print("[BOT] Bot Gemini Fleksibel berjalan...")
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
