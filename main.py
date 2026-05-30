import os
import io
import requests
import telebot
from PIL import Image
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from gradio_client import Client, handle_file
from flask import Flask
from threading import Thread

# ==========================================
# 1. SETUP TOKEN DAN KONEKSI
# ==========================================
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running and healthy!"

def run_web():
    # Koyeb biasanya menggunakan port 8000 atau 8080
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8000)))

# Jalankan web server di thread terpisah agar tidak memblokir bot
Thread(target=run_web, daemon=True).start()
# ----------------------------------------------

print("Menghubungkan ke server AI IDM-VTON...")
ai_client = Client("yisol/IDM-VTON")

# ==========================================
# 2. DATABASE KATALOG PRODUK
# ==========================================
KATALOG_BAJU = {
    "baju_1": {
        "nama": "Kaos Biru Polos", 
        "url_gambar": "https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?ixlib=rb-4.0.3&auto=format&fit=crop&w=600&q=80", 
        "link_beli": "https://tokokamu.com/beli/kaos-biru"
    },
    "baju_2": {
        "nama": "Jaket Kulit Hitam", 
        "url_gambar": "https://images.unsplash.com/photo-1551028719-00167b16eac5?ixlib=rb-4.0.3&auto=format&fit=crop&w=600&q=80", 
        "link_beli": "https://tokokamu.com/beli/jaket-hitam"
    }
}

# Memori sementara untuk mengingat pilihan pengguna
user_state = {}

# ==========================================
# FUNGSI TAMBAHAN: TOP CROP 2:3
# ==========================================
def top_crop_23(path_gambar):
    img = Image.open(path_gambar)
    w, h = img.size
    
    # Target rasio 2:3 (Lebar : Tinggi) -> Tinggi = Lebar * 1.5
    target_h = int(w * 1.5)
    
    if h >= target_h:
        # Jika gambar cukup tinggi, ambil lebar penuh, potong tingginya dari atas
        img = img.crop((0, 0, w, target_h))
    else:
        # Jika gambar kurang tinggi (landscape), potong lebarnya agar rasio 2:3
        new_w = int(h / 1.5)
        left = (w - new_w) / 2
        img = img.crop((left, 0, left + new_w, h))
        
    img.save(path_gambar)

# ==========================================
# 3. MENU UTAMA (Menampilkan Gambar Etalase)
# ==========================================
@bot.message_handler(commands=['start', 'coba_baju'])
def send_welcome(message):
    chat_id = message.chat.id
    bot.send_message(chat_id, "👋 Halo! Selamat datang di fitur AI Virtual Try-On.\n\nSilakan lihat etalase kami dan klik tombol pada gambar baju yang ingin kamu coba:")
    
    # Looping untuk mengirim setiap foto baju satu per satu
    for kode, detail in KATALOG_BAJU.items():
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(f"✨ Pilih {detail['nama']}", callback_data=kode))
        
        try:
            # Menyamar sebagai browser Chrome
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            response = requests.get(detail["url_gambar"], headers=headers)
            
            # Pastikan unduhan benar-benar sukses (kode 200 OK)
            if response.status_code != 200:
                raise Exception(f"Server gambar menolak akses (Status: {response.status_code})")
            
            # Ubah data menjadi file di dalam RAM
            img_bytes = io.BytesIO(response.content)
            
            # Beri tahu Telegram bahwa ini adalah file gambar JPG
            img_bytes.name = 'katalog.jpg' 
            
            bot.send_photo(
                chat_id=chat_id,
                photo=img_bytes,
                caption=f"👕 *{detail['nama']}*",
                parse_mode="Markdown",
                reply_markup=markup
            )
        except Exception as e:
            print(f"Gagal memproses {detail['nama']}: {e}")
            bot.send_message(
                chat_id=chat_id, 
                text=f"👕 *{detail['nama']}*\n_(Gambar gagal dimuat, namun tetap bisa dipilih)_", 
                parse_mode="Markdown", 
                reply_markup=markup
            )

# ==========================================
# 4. MENANGKAP KLIK TOMBOL PILIHAN BAJU
# ==========================================
@bot.callback_query_handler(func=lambda call: True)
def handle_pilihan_baju(call):
    pilihan = call.data
    chat_id = call.message.chat.id
    user_state[chat_id] = pilihan
    
    nama_baju = KATALOG_BAJU[pilihan]['nama']
    bot.send_message(chat_id, f"✅ Kamu memilih **{nama_baju}**.\n\nSekarang, silakan *upload* (kirim) foto diri kamu ke sini. Pastikan wajah dan minimal setengah badan terlihat jelas dengan cahaya yang terang ya!", parse_mode="Markdown")

# ==========================================
# 5. LOGIKA PEMROSESAN GAMBAR AI
# ==========================================
@bot.message_handler(content_types=['photo'])
def handle_foto_user(message):
    chat_id = message.chat.id
    
    if chat_id not in user_state:
        bot.reply_to(message, "❌ Kamu belum memilih baju. Ketik /start atau /coba_baju untuk memilih katalog terlebih dahulu.")
        return
        
    msg = bot.reply_to(message, "⏳ Memproses fotomu ke server AI... \n_Ini biasanya memakan waktu 30 - 60 detik. Mohon tunggu ya!_", parse_mode="Markdown")
    
    foto_user_path = f"user_{chat_id}.jpg"
    baju_path = f"baju_{chat_id}.jpg"
    
    try:
        baju_terpilih = KATALOG_BAJU[user_state[chat_id]]
        
        # Download foto user dari Telegram
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        with open(foto_user_path, 'wb') as new_file:
            new_file.write(downloaded_file)
            
        # Download foto produk dengan penyamaran header
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response_baju = requests.get(baju_terpilih["url_gambar"], headers=headers)
        with open(baju_path, 'wb') as file_baju:
            file_baju.write(response_baju.content)
            
        # Tembak ke server AI Hugging Face
        print(f"Mengirim permintaan VTON untuk user {chat_id}...")
        hasil_ai = ai_client.predict(
            dict(background=handle_file(foto_user_path), layers=[], composite=None), 
            handle_file(baju_path), 
            "Garment", 
            True,       
            True,       
            30,         
            42,         
            api_name="/tryon"
        )
        
        # Ambil hasil dan kembalikan ke Telegram
        hasil_gambar_path = hasil_ai[0] 
        
        # --- PROSES TOP CROP 2:3 ---
        top_crop_23(hasil_gambar_path)
        
        with open(hasil_gambar_path, 'rb') as foto_hasil:
            teks_promosi = f"✨ Tadaaa! Ini penampilanmu memakai {baju_terpilih['nama']}.\n\n🛒 Suka dengan bajunya? Beli langsung di sini: {baju_terpilih['link_beli']}"
            bot.send_photo(chat_id, foto_hasil, caption=teks_promosi)
            
    except Exception as e:
            with open("error.log", "a") as f:
                f.write(f"Error: {str(e)}\n")
            
            # Kirim error ke Telegram agar kamu tahu kenapa mati
            bot.reply_to(message, f"❌ Error terjadi: {str(e)}")
            bot.edit_message_text(f"❌ Server AI kebingungan memproses fotomu.\nPastikan wajah dan badanmu terlihat jelas tanpa terpotong!\n\n`Error Log: {str(e)}`", chat_id=msg.chat.id, message_id=msg.message_id, parse_mode="Markdown")
        
    finally:
        # Hapus pesan "memproses" dan bersihkan file sampah di server
        bot.delete_message(chat_id, msg.message_id)
        if os.path.exists(foto_user_path):
            os.remove(foto_user_path)
        if os.path.exists(baju_path):
            os.remove(baju_path)
        if chat_id in user_state:
            del user_state[chat_id]

# ==========================================
# 6. EKSEKUSI UTAMA
# ==========================================
if __name__ == "__main__":
    print("🚀 Bot VTON Toko Baju siap dan aktif 24/7...")
    bot.infinity_polling()