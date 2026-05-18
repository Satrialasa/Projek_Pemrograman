import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

DB_NAME = 'tutorsync_web.db'

class Database:
    @staticmethod
    def get_connection():
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def init_db():
        conn = Database.get_connection()
        # 1. Tabel SISWA
        conn.execute('''CREATE TABLE IF NOT EXISTS siswa (
            id_siswa INTEGER PRIMARY KEY AUTOINCREMENT, 
            nama_lengkap TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL, 
            tingkat_sekolah TEXT,
            kredit_saldo REAL DEFAULT 0
        )''')
        # 2. Tabel TUTOR
        conn.execute('''CREATE TABLE IF NOT EXISTS tutor (
            id_tutor INTEGER PRIMARY KEY AUTOINCREMENT, 
            nama_lengkap TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL, 
            spesialisasi_mapel TEXT, 
            tarif_per_jam REAL,
            status_verifikasi BOOLEAN DEFAULT 0,
            rating_akumulasi REAL DEFAULT 0
        )''')
        # 3. Tabel ADMINPLATFORM
        conn.execute('''CREATE TABLE IF NOT EXISTS adminplatform (
            id_admin INTEGER PRIMARY KEY AUTOINCREMENT, 
            nama_lengkap TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL, 
            level_akses TEXT
        )''')
        # 4. Tabel SESIBELAJAR
        conn.execute('''CREATE TABLE IF NOT EXISTS sesibelajar (
            id_sesi INTEGER PRIMARY KEY AUTOINCREMENT, 
            siswa_id INTEGER,
            tutor_id INTEGER,
            tanggal TEXT,
            waktu_mulai TEXT,
            waktu_selesai TEXT,
            status_sesi TEXT DEFAULT 'Menunggu',
            FOREIGN KEY(siswa_id) REFERENCES siswa(id_siswa),
            FOREIGN KEY(tutor_id) REFERENCES tutor(id_tutor)
        )''')
        # 5. Tabel TRANSAKSI
        conn.execute('''CREATE TABLE IF NOT EXISTS transaksi (
            id_transaksi INTEGER PRIMARY KEY AUTOINCREMENT,
            sesi_id INTEGER,
            nominal_bayar REAL,
            potongan_admin REAL,
            status_dana TEXT DEFAULT 'Ditahan',
            FOREIGN KEY(sesi_id) REFERENCES sesibelajar(id_sesi)
        )''')
        conn.commit()
        conn.close()

class Siswa:
    def __init__(self, id_siswa, nama_lengkap, email, tingkat_sekolah, kredit_saldo):
        self.id_siswa = id_siswa
        self.nama_lengkap = nama_lengkap
        self.email = email
        self.tingkat_sekolah = tingkat_sekolah
        self.kredit_saldo = kredit_saldo

    @staticmethod
    def login(email, password):
        conn = Database.get_connection()
        user = conn.execute('SELECT *, "siswa" as role FROM siswa WHERE email = ?', (email,)).fetchone()
        conn.close()
        if user and check_password_hash(user['password'], password):
            return user
        return None

    def cariTutor(self):
        conn = Database.get_connection()
        tutors = conn.execute('SELECT id_tutor, nama_lengkap, spesialisasi_mapel, tarif_per_jam FROM tutor').fetchall()
        conn.close()
        return tutors

    def bookingSesi(self, id_tutor, tanggal, waktu_mulai, waktu_selesai):
        conn = Database.get_connection()
        cursor = conn.cursor()
        cursor.execute('''INSERT INTO sesibelajar (siswa_id, tutor_id, tanggal, waktu_mulai, waktu_selesai, status_sesi) 
                          VALUES (?, ?, ?, ?, ?, "Menunggu")''', 
                       (self.id_siswa, id_tutor, tanggal, waktu_mulai, waktu_selesai))
        id_sesi = cursor.lastrowid
        conn.commit()
        conn.close()
        return id_sesi

class Tutor:
    def __init__(self, id_tutor, nama_lengkap, email, spesialisasi_mapel, tarif_per_jam, status_verifikasi, rating_akumulasi):
        self.id_tutor = id_tutor
        self.nama_lengkap = nama_lengkap
        self.email = email
        self.spesialisasi_mapel = spesialisasi_mapel
        self.tarif_per_jam = tarif_per_jam
        self.status_verifikasi = status_verifikasi
        self.rating_akumulasi = rating_akumulasi

    @staticmethod
    def login(email, password):
        conn = Database.get_connection()
        user = conn.execute('SELECT *, "tutor" as role FROM tutor WHERE email = ?', (email,)).fetchone()
        conn.close()
        if user and check_password_hash(user['password'], password):
            return user
        return None

    def menerimaBooking(self, id_sesi, is_accepted):
        status = "Dikonfirmasi" if is_accepted else "Ditolak"
        conn = Database.get_connection()
        conn.execute('UPDATE sesibelajar SET status_sesi = ? WHERE id_sesi = ? AND tutor_id = ?', 
                     (status, id_sesi, self.id_tutor))
        conn.commit()
        conn.close()

class AdminPlatform:
    def __init__(self, id_admin, nama_lengkap, email, level_akses):
        self.id_admin = id_admin
        self.nama_lengkap = nama_lengkap
        self.email = email
        self.level_akses = level_akses

    @staticmethod
    def login(email, password):
        conn = Database.get_connection()
        user = conn.execute('SELECT *, "admin" as role FROM adminplatform WHERE email = ?', (email,)).fetchone()
        conn.close()
        if user and check_password_hash(user['password'], password):
            return user
        return None

    def prosesPencairanDana(self, id_transaksi):
        conn = Database.get_connection()
        conn.execute('UPDATE transaksi SET status_dana = "Dicairkan ke Tutor" WHERE id_transaksi = ?', (id_transaksi,))
        conn.commit()
        conn.close()

class Transaksi:
    @staticmethod
    def buatTagihan(id_sesi, nominal):
        potongan = float(nominal) * 0.10 # Potongan admin 10%
        conn = Database.get_connection()
        conn.execute('''INSERT INTO transaksi (sesi_id, nominal_bayar, potongan_admin, status_dana) 
                        VALUES (?, ?, ?, "Ditahan")''', (id_sesi, nominal, potongan))
        conn.commit()
        conn.close()