# Gunakan versi Python yang ringan
FROM python:3.10-slim

# Set direktori kerja di dalam container
WORKDIR /app

# Salin file requirements dan instal library-nya
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Salin seluruh file kode (main.py, dll)
COPY . .

# Perintah untuk menjalankan bot saat server menyala
CMD ["python", "main.py"]