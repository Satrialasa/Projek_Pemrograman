from flask import Flask, render_template, request, redirect, url_for, session, flash
from models import Database, Siswa, Tutor, AdminPlatform, Transaksi
import sqlite3
from werkzeug.security import generate_password_hash

app = Flask(__name__)
app.secret_key = 'tutorsync_rahasia'

@app.route('/')
def index():
    if 'user_id' in session:
        if session['role'] == 'admin': return redirect(url_for('admin_dashboard'))
        return redirect(url_for('siswa_dashboard' if session['role'] == 'siswa' else 'tutor_dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        # Cek login di 3 tabel
        user = AdminPlatform.login(email, password)
        if not user: user = Siswa.login(email, password)
        if not user: user = Tutor.login(email, password)
            
        if user:
            # Simpan ID sesuai tabelnya
            id_key = 'id_admin' if user['role'] == 'admin' else ('id_siswa' if user['role'] == 'siswa' else 'id_tutor')
            session['user_id'] = user[id_key]
            session['role'] = user['role']
            session['nama_lengkap'] = user['nama_lengkap']
            return redirect(url_for('index'))
            
        flash('Email atau password salah!')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        role = request.form['role']
        nama = request.form['nama_lengkap']
        email = request.form['email']
        pw = generate_password_hash(request.form['password'])
        
        conn = Database.get_connection()
        try:
            if role == 'admin':
                conn.execute('INSERT INTO adminplatform (nama_lengkap, email, password, level_akses) VALUES (?, ?, ?, "Super Admin")', (nama, email, pw))
            elif role == 'siswa':
                tingkat = request.form.get('tingkat_sekolah', 'SMA')
                conn.execute('INSERT INTO siswa (nama_lengkap, email, password, tingkat_sekolah) VALUES (?, ?, ?, ?)', (nama, email, pw, tingkat))
            else:
                spesialisasi = request.form.get('spesialisasi')
                tarif = request.form.get('tarif')
                conn.execute('INSERT INTO tutor (nama_lengkap, email, password, spesialisasi_mapel, tarif_per_jam) VALUES (?, ?, ?, ?, ?)', 
                             (nama, email, pw, spesialisasi, tarif))
            conn.commit()
            flash('Registrasi Berhasil! Silakan Login.')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Email sudah terdaftar!')
        finally: 
            conn.close()
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/siswa')
def siswa_dashboard():
    if session.get('role') != 'siswa': return redirect('/')
    siswa_obj = Siswa(session['user_id'], session['nama_lengkap'], '', '', 0)
    tutors = siswa_obj.cariTutor()
    
    conn = Database.get_connection()
    bookings = conn.execute('''SELECT t.nama_lengkap as tutor_nama, s.tanggal, s.waktu_mulai, s.status_sesi 
                               FROM sesibelajar s JOIN tutor t ON s.tutor_id = t.id_tutor 
                               WHERE s.siswa_id = ?''', (session['user_id'],)).fetchall()
    conn.close()
    return render_template('siswa.html', tutors=tutors, bookings=bookings)

@app.route('/jadwal_tutor/<int:id_tutor>')
def lihat_jadwal(id_tutor):
    if session.get('role') != 'siswa': return redirect('/')
    conn = Database.get_connection()
    tutor = conn.execute('SELECT id_tutor, nama_lengkap, tarif_per_jam FROM tutor WHERE id_tutor = ?', (id_tutor,)).fetchone()
    conn.close()
    return render_template('booking.html', tutor=tutor)

@app.route('/book/<int:id_tutor>', methods=['POST'])
def book_jadwal(id_tutor):
    if session.get('role') != 'siswa': return redirect('/')
    tanggal = request.form['tanggal']
    waktu_mulai = request.form['waktu_mulai']
    waktu_selesai = request.form['waktu_selesai']
    
    siswa_obj = Siswa(session['user_id'], session['nama_lengkap'], '', '', 0)
    id_sesi = siswa_obj.bookingSesi(id_tutor, tanggal, waktu_mulai, waktu_selesai)
    
    # Buat Tagihan Otomatis
    conn = Database.get_connection()
    tarif = conn.execute('SELECT tarif_per_jam FROM tutor WHERE id_tutor = ?', (id_tutor,)).fetchone()['tarif_per_jam']
    conn.close()
    Transaksi.buatTagihan(id_sesi, tarif)
    
    flash('Booking berhasil diajukan! Menunggu konfirmasi dari tutor.')
    return redirect(url_for('siswa_dashboard'))

@app.route('/tutor')
def tutor_dashboard():
    if session.get('role') != 'tutor': return redirect('/')
    conn = Database.get_connection()
    pending = conn.execute('''SELECT s.id_sesi, sw.nama_lengkap as siswa_nama, s.tanggal, s.waktu_mulai 
                              FROM sesibelajar s JOIN siswa sw ON s.siswa_id = sw.id_siswa 
                              WHERE s.tutor_id = ? AND s.status_sesi = "Menunggu"''', (session['user_id'],)).fetchall()
    confirmed = conn.execute('''SELECT sw.nama_lengkap as siswa_nama, s.tanggal, s.waktu_mulai 
                              FROM sesibelajar s JOIN siswa sw ON s.siswa_id = sw.id_siswa 
                              WHERE s.tutor_id = ? AND s.status_sesi = "Dikonfirmasi"''', (session['user_id'],)).fetchall()
    conn.close()
    return render_template('tutor.html', tutor={'nama': session['nama_lengkap']}, pending_bookings=pending, confirmed_bookings=confirmed)

@app.route('/confirm/<int:id_sesi>/<action>', methods=['POST'])
def confirm_booking(id_sesi, action):
    if session.get('role') != 'tutor': return redirect('/')
    tutor_obj = Tutor(session['user_id'], session['nama_lengkap'], '', '', 0, 0, 0)
    tutor_obj.menerimaBooking(id_sesi, action == 'terima')
    flash('Status booking berhasil diubah!')
    return redirect(url_for('tutor_dashboard'))

@app.route('/admin')
def admin_dashboard():
    if session.get('role') != 'admin': return redirect('/')
    conn = Database.get_connection()
    transaksi = conn.execute('''SELECT t.id_transaksi, t.nominal_bayar, t.status_dana, tr.nama_lengkap as tutor_nama 
                                FROM transaksi t 
                                JOIN sesibelajar s ON t.sesi_id = s.id_sesi 
                                JOIN tutor tr ON s.tutor_id = tr.id_tutor''').fetchall()
    conn.close()
    return render_template('admin.html', transaksi=transaksi)

@app.route('/cairkan/<int:id_transaksi>', methods=['POST'])
def cairkan(id_transaksi):
    if session.get('role') != 'admin': return redirect('/')
    admin = AdminPlatform(session['user_id'], '', '', '')
    admin.prosesPencairanDana(id_transaksi)
    flash('Dana berhasil dicairkan ke Tutor!')
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    Database.init_db()
    app.run(debug=True, port=5000)