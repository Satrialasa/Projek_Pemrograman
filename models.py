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
        conn.execute('''CREATE TABLE IF NOT EXISTS siswa (
            id_siswa INTEGER PRIMARY KEY AUTOINCREMENT, nama_lengkap TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL, password TEXT NOT NULL, 
            tingkat_sekolah TEXT, kredit_saldo REAL DEFAULT 0
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS tutor (
            id_tutor INTEGER PRIMARY KEY AUTOINCREMENT, nama_lengkap TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL, password TEXT NOT NULL, 
            spesialisasi_mapel TEXT, tarif_per_jam REAL,
            status_verifikasi BOOLEAN DEFAULT 0, rating_akumulasi REAL DEFAULT 0,
            jadwal_ketersediaan TEXT DEFAULT 'Belum mengatur jadwal ketersediaan.'
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS adminplatform (
            id_admin INTEGER PRIMARY KEY AUTOINCREMENT, nama_lengkap TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL, password TEXT NOT NULL, level_akses TEXT
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS sesibelajar (
            id_sesi INTEGER PRIMARY KEY AUTOINCREMENT, siswa_id INTEGER,
            tutor_id INTEGER, tanggal TEXT, waktu_mulai TEXT, waktu_selesai TEXT,
            status_sesi TEXT DEFAULT 'Menunggu',
            FOREIGN KEY(siswa_id) REFERENCES siswa(id_siswa),
            FOREIGN KEY(tutor_id) REFERENCES tutor(id_tutor)
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS transaksi (
            id_transaksi INTEGER PRIMARY KEY AUTOINCREMENT, sesi_id INTEGER,
            nominal_bayar REAL, potongan_admin REAL, status_dana TEXT DEFAULT 'Ditahan',
            FOREIGN KEY(sesi_id) REFERENCES sesibelajar(id_sesi)
        )''')
        conn.commit()
        conn.close()

class SesiBelajar:
    def __init__(self, id_sesi, tanggal, waktu_mulai, waktu_selesai, status_sesi, siswa_id=None, tutor_id=None):
        self.id_sesi = id_sesi
        self.tanggal = tanggal
        self.waktu_mulai = waktu_mulai
        self.waktu_selesai = waktu_selesai
        self.status_sesi = status_sesi
        self.siswa_id = siswa_id
        self.tutor_id = tutor_id

    def generateLinkMeeting(self):
        return f"https://meet.tutorsync.com/sesi-{self.id_sesi}"

    def tandaiSelesai(self):
        conn = Database.get_connection()
        conn.execute('UPDATE sesibelajar SET status_sesi = "Selesai" WHERE id_sesi = ?', (self.id_sesi,))
        conn.commit()
        conn.close()
        self.status_sesi = "Selesai"

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

    def cariTutor(self, keyword=""):
        conn = Database.get_connection()
        if keyword:
            query_str = f"%{keyword}%"
            tutors = conn.execute('''
                SELECT id_tutor, nama_lengkap, spesialisasi_mapel, tarif_per_jam 
                FROM tutor 
                WHERE nama_lengkap LIKE ? OR spesialisasi_mapel LIKE ?
            ''', (query_str, query_str)).fetchall()
        else:
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

    def bayarTagihan(self, id_sesi):
        # Mengubah status menjadi Dikonfirmasi setelah siswa membayar
        conn = Database.get_connection()
        conn.execute('UPDATE sesibelajar SET status_sesi = "Dikonfirmasi" WHERE id_sesi = ? AND siswa_id = ?', 
                     (id_sesi, self.id_siswa))
        conn.commit()
        conn.close()

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

    def aturJadwalKosong(self, teks_jadwal):
        conn = Database.get_connection()
        conn.execute('UPDATE tutor SET jadwal_ketersediaan = ? WHERE id_tutor = ?', (teks_jadwal, self.id_tutor))
        conn.commit()
        conn.close()

    def menerimaBooking(self, id_sesi, is_accepted):
        # Berubah menjadi Menunggu Pembayaran, bukan langsung Dikonfirmasi
        status = "Menunggu Pembayaran" if is_accepted else "Ditolak"
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
        potongan = float(nominal) * 0.10
        conn = Database.get_connection()
        conn.execute('''INSERT INTO transaksi (sesi_id, nominal_bayar, potongan_admin, status_dana) 
                        VALUES (?, ?, ?, "Ditahan")''', (id_sesi, nominal, potongan))
        conn.commit()
        conn.close()
