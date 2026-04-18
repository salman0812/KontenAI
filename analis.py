import requests
import json
import time
import os
from datetime import datetime

APIFY_TOKEN = os.environ.get("APIFY_TOKEN")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

ACTOR_ID = "GdWCkxBtKWOsKjdch"

def run_apify_scraper():
    print("[APIFY] Memulai scraping TikTok...")
    
    input_data = {
        "searchQueries": ["alam indonesia", "petualangan alam", "masak besar", "fyp"],
        "resultsPerPage": 10,
        "searchSorting": "0",
        "searchDatePosted": "2",
        "leastDiggs": 500,
        "proxyConfiguration": {"useApifyProxy": True}
    }
    
    run_url = f"https://api.apify.com/v2/acts/{ACTOR_ID}/runs"
    headers = {"Authorization": f"Bearer {APIFY_TOKEN}", "Content-Type": "application/json"}
    
    response = requests.post(run_url, headers=headers, json=input_data)
    if response.status_code != 201:
        print(f"[APIFY] Gagal menjalankan actor: {response.text}")
        return []
    
    run_id = response.json()["data"]["id"]
    print(f"[APIFY] Scraper berjalan. Run ID: {run_id}")
    
    for i in range(36):
        time.sleep(5)
        status_url = f"{run_url}/{run_id}"
        status_res = requests.get(status_url, headers=headers)
        status = status_res.json()["data"]["status"]
        if status == "SUCCEEDED":
            print("[APIFY] Scraping selesai.")
            break
        elif status == "FAILED":
            print("[APIFY] Scraping gagal.")
            return []
    
    dataset_url = f"https://api.apify.com/v2/acts/{ACTOR_ID}/runs/{run_id}/dataset/items"
    data_res = requests.get(dataset_url, headers=headers)
    videos = data_res.json()
    print(f"[APIFY] Berhasil mengambil {len(videos)} video.")
    return videos

def analyze_with_groq(videos):
    if not videos:
        return "Tidak ada video yang berhasil diambil."
    
    filtered = [v for v in videos if v.get("playCount", 0) > 30000]
    if not filtered:
        return "Tidak ada video dengan views di atas 30.000."
    
    top_videos = sorted(filtered, key=lambda x: x.get("playCount", 0), reverse=True)[:5]
    
    report_text = "Data video viral (views > 30K):\n"
    for i, v in enumerate(top_videos, 1):
        report_text += f"{i}. Akun: @{v.get('authorMeta', {}).get('name', 'unknown')}\n"
        report_text += f"   Teks: {v.get('text', '')}\n"
        report_text += f"   Views: {v.get('playCount', 0)}, Likes: {v.get('diggCount', 0)}\n\n"
    
    prompt_groq = f"""
Kamu adalah analis konten viral. Analisis data video TikTok berikut:

{report_text}

Tugas:
1. Pilih 3 video terbaik yang paling cocok ditiru untuk konten bertema alam, petualangan, atau masak tradisional.
2. Untuk setiap video, jelaskan kenapa video itu viral.
3. Buat prompt siap pakai untuk Gemini agar karakter "Mang Baduy" bisa berakting di adegan serupa.

Tulis hasil analisis dalam format yang rapi dan mudah dibaca.
"""
    
    print("[GROQ] Mengirim data untuk dianalisis...")
    groq_url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    data = {"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt_groq}], "temperature": 0.7}
    
    response = requests.post(groq_url, headers=headers, json=data)
    if response.status_code == 200:
        return response.json()["choices"][0]["message"]["content"]
    else:
        return f"Gagal analisis Groq: {response.text}"

def send_to_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    max_len = 4000
    if len(message) > max_len:
        parts = [message[i:i+max_len] for i in range(0, len(message), max_len)]
        for part in parts:
            requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": part})
            time.sleep(1)
    else:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message})
    print("[TELEGRAM] Pesan terkirim.")

if __name__ == "__main__":
    print("=" * 50)
    print("ANALIS KONTEN OTOMATIS")
    print(f"Waktu: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} WIB")
    print("=" * 50)
    
    videos = run_apify_scraper()
    hasil = analyze_with_groq(videos)
    
    pesan = f"""
LAPORAN ANALIS KONTEN HARIAN
Tanggal: {datetime.now().strftime('%Y-%m-%d')}
Jam: {datetime.now().strftime('%H:%M')} WIB

{hasil}

---
Siap dieksekusi.
"""
    send_to_telegram(pesan.strip())
    print("Selesai.")
