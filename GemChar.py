import requests
import json
import time
import os
import base64
import google.generativeai as genai

# ==========================================
# AMBIL API KEYS DARI ENVIRONMENT
# ==========================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Konfigurasi Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.ImageGenerationModel("models/gemini-3-pro-image-preview")

# ==========================================
# FUNGSI: DOWNLOAD GAMBAR DARI TELEGRAM
# ==========================================
def download_telegram_image(file_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile"
    response = requests.post(url, data={"file_id": file_id})
    
    if response.status_code != 200:
        return None
    
    file_path = response.json()["result"]["file_path"]
    file_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
    
    image_data = requests.get(file_url).content
    return image_data

# ==========================================
# FUNGSI: PARSE PROMPT 4 ADEGAN
# ==========================================
def parse_adegan_prompt(user_text):
    # Cari pemisah "### FRAME PROMPT ###"
    if "### FRAME PROMPT ###" not in user_text:
        return None
    
    parts = user_text.split("### FRAME PROMPT ###")
    if len(parts) < 2:
        return None
    
    frame_part = parts[1].strip()
    
    # Split per baris
    adegan_list = [line.strip() for line in frame_part.split('\n') if line.strip()]
    
    # Ambil maksimal 4 adegan
    return adegan_list[:4]

# ==========================================
# FUNGSI: GENERATE 1 FRAME DENGAN GEMINI
# ==========================================
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
        response = model.generate_images(
            prompt=full_prompt,
            reference_images=[reference_image_data],
            number_of_images=1
        )
        
        return response.images[0]
    except Exception as e:
        print(f"[GEMINI] Error adegan {index}: {e}")
        return None

# ==========================================
# FUNGSI: KIRIM GAMBAR KE TELEGRAM
# ==========================================
def send_image_to_telegram(chat_id, image_data, caption=""):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    
    files = {"photo": ("frame.jpg", image_data, "image/jpeg")}
    data = {"chat_id": chat_id, "caption": caption}
    
    response = requests.post(url, files=files, data=data)
    return response.status_code == 200

# ==========================================
# FUNGSI: KIRIM PESAN TEKS KE TELEGRAM
# ==========================================
def send_message_to_telegram(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text}
    requests.post(url, data=data)

# ==========================================
# FUNGSI UTAMA: PROSES UPDATE DARI TELEGRAM
# ==========================================
def process_telegram_update(update):
    if "message" not in update:
        return
    
    message = update["message"]
    chat_id = message["chat"]["id"]
    
    # Cek apakah ada foto
    if "photo" not in message:
        send_message_to_telegram(chat_id, "Silakan kirim FOTO karakter + prompt 4 adegan.")
        return
    
    # Cek apakah ada caption (prompt)
    if "caption" not in message:
        send_message_to_telegram(chat_id, "Silakan tulis prompt 4 adegan di caption foto.")
        return
    
    # Ambil file_id foto terbesar (resolusi tertinggi)
    photo = message["photo"][-1]
    file_id = photo["file_id"]
    caption = message["caption"]
    
    # Parse prompt
    adegan_list = parse_adegan_prompt(caption)
    
    if not adegan_list or len(adegan_list) == 0:
        send_message_to_telegram(chat_id, "Format prompt salah. Gunakan:\n### FRAME PROMPT ###\nAdegan 1\nAdegan 2\nAdegan 3\nAdegan 4")
        return
    
    send_message_to_telegram(chat_id, f"Memproses {len(adegan_list)} adegan... Mohon tunggu 1-2 menit.")
    
    # Download gambar referensi
    reference_image = download_telegram_image(file_id)
    if not reference_image:
        send_message_to_telegram(chat_id, "Gagal download gambar.")
        return
    
    # Generate 4 frame
    for i, adegan in enumerate(adegan_list, 1):
        frame_image = generate_frame(reference_image, adegan, i)
        
        if frame_image:
            # Convert PIL Image to bytes
            from io import BytesIO
            img_bytes = BytesIO()
            frame_image.save(img_bytes, format="JPEG")
            img_bytes.seek(0)
            
            send_image_to_telegram(chat_id, img_bytes.getvalue(), f"Adegan {i}: {adegan}")
        else:
            send_message_to_telegram(chat_id, f"Gagal generate adegan {i}.")
    
    send_message_to_telegram(chat_id, "Semua adegan selesai diproses.")

# ==========================================
# MAIN LOOP UNTUK POLLING TELEGRAM
# ==========================================
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
