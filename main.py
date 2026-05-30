import os
import io
import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from gradio_client import Client, handle_file

# 1. SETUP TOKEN DAN BOT
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

# 2. SETUP KONEKSI AI
print("Menghubungkan ke server AI IDM-VTON...")
ai_client = Client("yisol/IDM-VTON")

# 3. DATABASE KATALOG PRODUK
KATALOG_BAJU = {
    "baju_1": {
        "nama": "Kaos Biru Polos", 
        "url_gambar": "https://upload.wikimedia.org/wikipedia/commons/2/24/Blue_Tshirt.jpg", 
        "link_beli": "https://tokokamu.com/beli/kaos-biru"
    },
    "baju_2": {
        "nama": "Jaket Kulit Hitam", 
        "url_gambar": "https://upload.wikimedia.org/wikipedia/commons/a/a9/Black_leather_jacket.jpg", 
        "link_beli": "https://tokokamu.com/beli/jaket-hitam"
    }
}

# Memori sementara untuk mengingat pilihan pengguna
user_state = {}

# 4. MENU UTAMA (Menampilkan Gambar Etalase)
@bot.message_handler(commands=['start', 'coba_baju'])
def send_welcome(message):
    chat_id = message.chat.id
    bot.send_message(chat_id, "👋 Halo! Selamat datang di fitur AI Virtual Try-On.\n\nSilakan lihat etalase kami dan klik tombol pada gambar baju yang ingin kamu coba:")
    
    # Looping untuk mengirim setiap foto baju satu per satu
    for kode, detail in KATALOG_BAJU.items():
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(f"✨ Pilih {detail['nama']}", callback_data=kode))
        
        try:
            # Menyamar sebagai browser Chrome agar tidak diblokir Wikimedia
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            response = requests.get(detail["url_gambar"], headers=headers)
            
            # Ubah data dari internet langsung menjadi file gambar di dalam RAM
            img_bytes = io.BytesIO(response.content)
            
            bot.send_photo(
                chat_id=chat_id,
                photo=img_bytes,
                caption=f"👕 *{detail['nama']}*",
                parse_mode="Markdown",
                reply_markup=markup
            )
        except Exception as e:
            # Fallback jika gambar tetap gagal dimuat, teksnya saja yang dikirim
            print(f"Gagal memproses {detail['nama']}: {e}")
            bot.send_message(
                chat_id=chat_id, 
                text=f"👕 *{detail['nama']}*\n_(Gambar gagal dimuat, namun tetap bisa dipilih)_", 
                parse_mode="Markdown", 
                reply_markup=markup
            )

# 5. MENANGKAP KLIK TOMBOL PILIHAN BAJU
@bot.callback_query_handler(func=lambda call: True)
def handle_pilihan_baju(call):
    pilihan = call.data
    chat_id = call.message.chat.id
    user_state[chat_id] = pilihan
    
    nama_baju = KATALOG_BAJU[pilihan]['nama']
    bot.send_message(chat_id, f"✅ Kamu memilih **{nama_baju}**.\n\nSekarang, silakan *upload* (kirim) foto diri kamu ke sini. Pastikan wajah dan minimal setengah badan terlihat jelas dengan cahaya yang terang ya!", parse_mode="Markdown")

# 6. LOGIKA PEMROSESAN GAMBAR AI
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
            
        # Download foto produk dengan penyamaran header agar tidak diblokir
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
        with open(hasil_gambar_path, 'rb') as foto_hasil:
            teks_promosi = f"✨ Tadaaa! Ini penampilanmu memakai {baju_terpilih['nama']}.\n\n🛒 Suka dengan bajunya? Beli langsung di sini: {baju_terpilih['link_beli']}"
            bot.send_photo(chat_id, foto_hasil, caption=teks_promosi)
            
    except Exception as e:
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

if __name__ == "__main__":
    print("🚀 Bot VTON Toko Baju siap dan aktif 24/7...")
    bot.infinity_polling()