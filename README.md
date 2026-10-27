# EduTask Smart Deadline Reminder

Prototipe web berbasis Python + Flask + SQLite dengan antarmuka responsif. Mengikuti arah visual dari file mockup EduTask yang disertakan pengguna. Database dibuat otomatis saat aplikasi pertama kali dijalankan.

## Fitur
- Mahasiswa: registrasi NIM, program studi, password + konfirmasi, simulasi pembayaran, login, dashboard statistik, daftar tugas, update progres, kalender akademik, notifikasi, riwayat.
- Dosen: registrasi, memilih program studi dan mata kuliah yang diampu, dashboard, CRUD tugas, kalender ujian, notifikasi pembaruan progres, riwayat.
- Filter tugas dan jadwal berdasarkan program studi; dosen hanya bisa mengelola tugasnya sendiri dan pilihan mata kuliah yang didaftarkan.
- Admin demo: ringkasan mahasiswa, dosen, tugas, dan aktivitas.
- Data disimpan secara lokal di SQLite (`edutask.db`), bukan hanya di memori browser.

## Cara menjalankan di Windows
1. Ekstrak ZIP ke folder, misalnya `C:\Project\edutask_smart_deadline_reminder`.
2. Instal Python 3.10 atau lebih baru dari https://www.python.org/downloads/ dan centang **Add Python to PATH**.
3. Buka Command Prompt/Terminal di folder proyek.
4. Buat virtual environment:
   ```bat
   py -m venv .venv
   ```
5. Aktifkan environment:
   ```bat
   .venv\Scripts\activate
   ```
6. Instal dependensi:
   ```bat
   python -m pip install -r requirements.txt
   ```
7. Jalankan aplikasi:
   ```bat
   python app.py
   ```
8. Buka `http://127.0.0.1:5000` di browser.

## Akun demo
- Dosen: ID `dosen001`, password `dosen123` (mengampu Sistem Informasi Manajemen untuk prodi Sistem Informasi).
- Admin: ID `admin`, password `admin123`.
- Mahasiswa: daftar akun sendiri, lalu selesaikan simulasi pembayaran. Untuk melihat tugas dosen demo, pilih prodi **Sistem Informasi**.

## Catatan penting
- Pembayaran hanya simulasi: tidak ada transaksi atau integrasi pembayaran sungguhan.
- Ini prototipe untuk demo lokal/tugas kuliah, belum siap untuk produksi. Sebelum dipublikasikan, ganti `secret_key`, matikan `debug`, gunakan HTTPS, tambahkan proteksi CSRF, kebijakan password dan otorisasi yang lebih lengkap, serta tinjau keamanan dan privasi data.
- Tanggal deadline dan ujian mengikuti tanggal kalender komputer/server yang menjalankan aplikasi.
- Reset data demo: hentikan server, hapus file `edutask.db`, lalu jalankan `python app.py` lagi. Penghapusan database menghapus semua akun/tugas lokal.
