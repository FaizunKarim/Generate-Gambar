import os
import io
import requests
import telebot
import cv2
import numpy as np
from PIL import Image
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from gradio_client import Client, handle_file

# 1. SETUP BOT
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

# 2. SETUP KONEKSI AI
print("Menghubungkan ke server AI IDM-VTON...")
ai_client = Client("yisol/IDM-VTON")

# 3. DATABASE KATALOG PRODUK
KATALOG_BAJU = {
    "baju_1": {
        "nama": "Kaos Biru Polos", 
        "url_gambar": "https://m.media-amazon.com/images/I/51wXhSNGFHL._AC_UX679_.jpg", 
        "link_beli": "https://tokokamu.com/beli/kaos-biru",
        "prompt_ai": "A plain blue short-sleeve t-shirt, realistic, high quality"
    },
    "baju_2": {
        "nama": "Jaket Kulit Hitam", 
        "url_gambar": "https://images.unsplash.com/photo-1551028719-00167b16eac5?ixlib=rb-4.0.3&auto=format&fit=crop&w=600&q=80", 
        "link_beli": "https://tokokamu.com/beli/jaket-hitam",
        "prompt_ai": "A black leather jacket, long sleeves, front open, realistic"
    }
}

user_state = {}

@bot.message_handler(commands=['start', 'coba_baju'])
def send_welcome(message):
    chat_id = message.chat.id
    bot.send_message(chat_id, "👋 Halo! Selamat datang di fitur AI Virtual Try-On.\n\nSilakan pilih baju yang ingin kamu coba:")
    for kode, detail in KATALOG_BAJU.items():
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(f"✨ Pilih {detail['nama']}", callback_data=kode))
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(detail["url_gambar"], headers=headers)
            img_bytes = io.BytesIO(response.content)
            img_bytes.name = 'katalog.jpg'
            bot.send_photo(chat_id, img_bytes, caption=f"👕 *{detail['nama']}*", parse_mode="Markdown", reply_markup=markup)
        except Exception:
            bot.send_message(chat_id, f"👕 {detail['nama']} (Gambar gagal dimuat)", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_pilihan_baju(call):
    user_state[call.message.chat.id] = call.data
    bot.send_message(call.message.chat.id, f"✅ Kamu memilih {KATALOG_BAJU[call.data]['nama']}.\n\n📸 Sekarang, kirim fotomu (setengah badan, posisi tegak).")

@bot.message_handler(content_types=['photo'])
def handle_foto_user(message):
    chat_id = message.chat.id
    if chat_id not in user_state:
        bot.reply_to(message, "❌ Pilih baju dulu dengan /start.")
        return
        
    msg = bot.reply_to(message, "⏳ Memproses fotomu ke server AI... Mohon tunggu.")
    foto_user_path = f"user_{chat_id}.jpg"
    baju_path = f"baju_{chat_id}.jpg"
    
    try:
        # Download & Pre-processing (Padding Dinamis)
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        with open(foto_user_path, 'wb') as f: f.write(downloaded_file)
        
        img = Image.open(foto_user_path)
        cv_img = np.array(img.convert('RGB'))[:, :, ::-1].copy()
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        faces = face_cascade.detectMultiScale(cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY), 1.1, 5)
        
        canvas_size = int(max(img.size) * 1.2)
        kanvas = Image.new("RGB", (canvas_size, canvas_size), (255, 255, 255))
        
        pos_x, pos_y = (canvas_size - img.size[0])//2, (canvas_size - img.size[1])//2
        if len(faces) > 0:
            x, y, w, h = sorted(faces, key=lambda f: f[2]*f[3], reverse=True)[0]
            pos_y = int(canvas_size * 0.15) - y
            
        kanvas.paste(img, (pos_x, max(0, min(pos_y, canvas_size - img.size[1]))))
        kanvas.save(foto_user_path)

        # Proses AI
        response_baju = requests.get(KATALOG_BAJU[user_state[chat_id]]["url_gambar"], headers={'User-Agent': 'Mozilla/5.0'})
        with open(baju_path, 'wb') as f: f.write(response_baju.content)
            
        hasil_ai = ai_client.predict(
            dict(background=handle_file(foto_user_path), layers=[], composite=None), 
            handle_file(baju_path), 
            KATALOG_BAJU[user_state[chat_id]]["prompt_ai"], 
            False, True, 30, 42, api_name="/tryon"
        )
        
        with open(hasil_ai[0], 'rb') as f:
            bot.send_photo(chat_id, f, caption="✨ Hasil Try-On kamu!")
        bot.delete_message(chat_id, msg.message_id)
            
    except Exception as e:
        bot.edit_message_text(f"❌ Server AI gagal memproses.\nLog: {str(e)}", chat_id, msg.message_id)
    finally:
        for p in [foto_user_path, baju_path]:
            if os.path.exists(p): os.remove(p)
        if chat_id in user_state: del user_state[chat_id]

if __name__ == "__main__":
    bot.infinity_polling()