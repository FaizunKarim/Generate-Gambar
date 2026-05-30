import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from gradio_client import Client, handle_file

# 🔧 AMBIL KUNCI RAHASIA DARI ENVIRONMENT
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
HF_TOKEN = os.getenv("HF_TOKEN")

bot = telebot.TeleBot(TOKEN)

# 🤖 HUBUNGKAN KE SERVER AI HUGGING FACE DENGAN TOKEN
print("Menghubungkan ke server AI IDM-VTON...")
ai_client = Client("yisol/IDM-VTON")

# 👕 DATABASE KATALOG BAJU (FOTO RANDOM UNTUK TESTING)
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

# Menyimpan memori sementara (siapa memilih baju apa)
user_state = {}

@bot.message_handler(commands=['start', 'coba_baju'])
def send_welcome(message):
    markup = InlineKeyboardMarkup()
    for kode, detail in KATALOG_BAJU.items():
        markup.add(InlineKeyboardButton(detail["nama"], callback_data=kode))
    
    bot.reply_to(message, "👋 Halo! Selamat datang di fitur AI Virtual Try-On.\n\nPilih baju yang ingin kamu coba dari etalase kami:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_pilihan_baju(call):
    pilihan = call.data
    chat_id = call.message.chat.id
    user_state[chat_id] = pilihan
    
    nama_baju = KATALOG_BAJU[pilihan]['nama']
    bot.send_message(chat_id, f"✅ Kamu memilih **{nama_baju}**.\n\nSekarang, silakan *upload* (kirim) foto diri kamu ke sini. Pastikan wajah dan badan menghadap ke depan dengan cahaya yang terang ya!", parse_mode="Markdown")

@bot.message_handler(content_types=['photo'])
def handle_foto_user(message):
    chat_id = message.chat.id
    
    if chat_id not in user_state:
        bot.reply_to(message, "❌ Kamu belum memilih baju. Ketik /start atau /coba_baju untuk memilih katalog terlebih dahulu.")
        return
        
    msg = bot.reply_to(message, "⏳ Memproses fotomu ke server AI... \n_Ini biasanya memakan waktu 30 - 60 detik. Mohon tunggu ya!_", parse_mode="Markdown")
    
    try:
        baju_terpilih = KATALOG_BAJU[user_state[chat_id]]
        
        # 1. Download foto yang dikirim user dari Telegram
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        foto_user_path = f"user_{chat_id}.jpg"
        with open(foto_user_path, 'wb') as new_file:
            new_file.write(downloaded_file)
            
        # 2. Kirim gambar ke AI IDM-VTON untuk dijahit virtual
        print(f"Mengirim permintaan VTON untuk user {chat_id}...")
        hasil_ai = ai_client.predict(
            dict(background=handle_file(foto_user_path), layers=[], composite=None), # Foto User
            handle_file(baju_terpilih["url_gambar"]), # Foto Produk
            "Garment", # Mode background
            True,      # Gunakan auto-crop
            True,      # Gunakan auto-mask
            30,        # Denoising steps (kualitas standar)
            42,        # Seed
            api_name="/tryon"
        )
        
        # 3. Ambil foto hasil kembalian dari AI dan kirim ke Telegram
        hasil_gambar_path = hasil_ai[0] 
        with open(hasil_gambar_path, 'rb') as foto_hasil:
            teks_promosi = f"✨ Tadaaa! Ini penampilanmu memakai {baju_terpilih['nama']}.\n\n🛒 Suka dengan bajunya? Beli langsung di sini: {baju_terpilih['link_beli']}"
            bot.send_photo(chat_id, foto_hasil, caption=teks_promosi)
            
        # 4. Bersihkan file lokal agar memori server tidak penuh
        bot.delete_message(chat_id, msg.message_id) # Hapus pesan "⏳ Memproses..."
        if os.path.exists(foto_user_path):
            os.remove(foto_user_path)
        del user_state[chat_id]
        
    except Exception as e:
        bot.edit_message_text(f"❌ Yah, gagal memproses foto. Kemungkinan server AI sedang penuh.\n\n`Error Log: {str(e)}`", chat_id=msg.chat.id, message_id=msg.message_id, parse_mode="Markdown")
        if chat_id in user_state:
            del user_state[chat_id]

if __name__ == "__main__":
    print("🚀 Bot VTON Toko Baju siap dan aktif 24/7...")
    bot.infinity_polling()