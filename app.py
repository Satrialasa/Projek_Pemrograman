from flask import Flask, render_template, request, redirect, url_for, session, flash
from models import Database, Siswa, Tutor, AdminPlatform, Transaksi, SesiBelajar
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
        
        user = AdminPlatform.login(email, password)
        if not user: user = Siswa.login(email, password)
        if not user: user = Tutor.login(email, password)
            
        if user:
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
    
    keyword = request.args.get('q', '')
    tutors = siswa_obj.cariTutor(keyword)
    
    conn = Database.get_connection()
    bookings = conn.execute('''SELECT s.id_sesi, t.nama_lengkap as tutor_nama, s.tanggal, s.waktu_mulai, s.status_sesi 
                               FROM sesibelajar s JOIN tutor t ON s.tutor_id = t.id_tutor 
                               WHERE s.siswa_id = ?''', (session['user_id'],)).fetchall()
    conn.close()
    
    sesi_list = []
    for b in bookings:
        sb = SesiBelajar(b['id_sesi'], b['tanggal'], b['waktu_mulai'], '', b['status_sesi'])
        sesi_list.append({
            'id_sesi': b['id_sesi'],
            'tutor_nama': b['tutor_nama'],
            'waktu': f"{b['tanggal']} | {b['waktu_mulai']}",
            'status': b['status_sesi'],
            'link_meet': sb.generateLinkMeeting() if b['status_sesi'] == 'Dikonfirmasi' else '#'
        })
        
    return render_template('siswa.html', tutors=tutors, bookings=sesi_list, keyword=keyword)

@app.route('/jadwal_tutor/<int:id_tutor>')
def lihat_jadwal(id_tutor):
    if session.get('role') != 'siswa': return redirect('/')
    conn = Database.get_connection()
    tutor = conn.execute('SELECT id_tutor, nama_lengkap, tarif_per_jam, jadwal_ketersediaan FROM tutor WHERE id_tutor = ?', (id_tutor,)).fetchone()
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
    
    conn = Database.get_connection()
    tarif = conn.execute('SELECT tarif_per_jam FROM tutor WHERE id_tutor = ?', (id_tutor,)).fetchone()['tarif_per_jam']
    conn.close()
    
    Transaksi.buatTagihan(id_sesi, tarif)
    flash('Pengajuan sesi bimbingan berhasil dikirim!')
    return redirect(url_for('siswa_dashboard'))

# Rute baru untuk mensimulasikan pembayaran siswa
@app.route('/bayar/<int:id_sesi>', methods=['POST'])
def bayar_tagihan(id_sesi):
    if session.get('role') != 'siswa': return redirect('/')
    siswa_obj = Siswa(session['user_id'], session['nama_lengkap'], '', '', 0)
    siswa_obj.bayarTagihan(id_sesi)
    flash('Pembayaran berhasil! Link pertemuan sekarang sudah tersedia.')
    return redirect(url_for('siswa_dashboard'))

@app.route('/tutor')
def tutor_dashboard():
    if session.get('role') != 'tutor': return redirect('/')
    conn = Database.get_connection()
    
    profil = conn.execute('SELECT jadwal_ketersediaan FROM tutor WHERE id_tutor = ?', (session['user_id'],)).fetchone()
    
    pending = conn.execute('''SELECT s.id_sesi, sw.nama_lengkap as siswa_nama, s.tanggal, s.waktu_mulai 
                              FROM sesibelajar s JOIN siswa sw ON s.siswa_id = sw.id_siswa 
                              WHERE s.tutor_id = ? AND s.status_sesi = "Menunggu"''', (session['user_id'],)).fetchall()
                              
    confirmed = conn.execute('''SELECT s.id_sesi, sw.nama_lengkap as siswa_nama, s.tanggal, s.waktu_mulai, s.status_sesi 
                              FROM sesibelajar s JOIN siswa sw ON s.siswa_id = sw.id_siswa 
                              WHERE s.tutor_id = ? AND s.status_sesi IN ("Menunggu Pembayaran", "Dikonfirmasi")''', (session['user_id'],)).fetchall()
    conn.close()
    
    # Generate Link Meet untuk Dasbor Tutor
    confirmed_list = []
    for c in confirmed:
        sb = SesiBelajar(c['id_sesi'], c['tanggal'], c['waktu_mulai'], '', c['status_sesi'])
        confirmed_list.append({
            'id_sesi': c['id_sesi'],
            'siswa_nama': c['siswa_nama'],
            'tanggal': c['tanggal'],
            'waktu_mulai': c['waktu_mulai'],
            'status_sesi': c['status_sesi'],
            'link_meet': sb.generateLinkMeeting() if c['status_sesi'] == 'Dikonfirmasi' else '#'
        })
        
    return render_template('tutor.html', tutor={'nama': session['nama_lengkap'], 'jadwal_ketersediaan': profil['jadwal_ketersediaan']}, pending_bookings=pending, confirmed_bookings=confirmed_list)

@app.route('/atur_jadwal', methods=['POST'])
def atur_jadwal():
    if session.get('role') != 'tutor': return redirect('/')
    teks_jadwal = request.form['jadwal_ketersediaan']
    tutor_obj = Tutor(session['user_id'], session['nama_lengkap'], '', '', 0, 0, 0)
    tutor_obj.aturJadwalKosong(teks_jadwal)
    flash('Informasi ketersediaan jadwal berhasil diperbarui!')
    return redirect(url_for('tutor_dashboard'))

@app.route('/confirm/<int:id_sesi>/<action>', methods=['POST'])
def confirm_booking(id_sesi, action):
    if session.get('role') != 'tutor': return redirect('/')
    tutor_obj = Tutor(session['user_id'], session['nama_lengkap'], '', '', 0, 0, 0)
    tutor_obj.menerimaBooking(id_sesi, action == 'terima')
    if action == 'terima':
        flash('Jadwal diterima. Menunggu pembayaran dari siswa.')
    return redirect(url_for('tutor_dashboard'))

@app.route('/selesai/<int:id_sesi>', methods=['POST'])
def sesi_selesai(id_sesi):
    if session.get('role') != 'tutor': return redirect('/')
    sesi_obj = SesiBelajar(id_sesi, '', '', '', 'Dikonfirmasi')
    sesi_obj.tandaiSelesai()
    flash('Sesi belajar ditandai Selesai. Menunggu verifikasi pencairan dana Admin!')
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
