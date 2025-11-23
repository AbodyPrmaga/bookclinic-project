from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import sqlite3
import json
from datetime import datetime, timedelta
import threading
import requests
import logging
import time
import os

# إعداد التسجيل
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
app.secret_key = b'\xfd{H\xe5<\x95\xf9\xe3\x96.5\xd1\x01O<!\xd5\xa2\xa0\x9fR"\xa1\xa8\x12\x1c!\x8b\x84\xeb\x1b\x99\x95\x8c\xb0\xce\xf7\x91\x07\x19\x9d\x04\xb6\x92l\xaf\x15\x0e\xc4\xa2\xbe\xfez\xa0\x91\x10\x88\xc8\x89\x1d\xf1\x15\x13\x9a'

# تكوين قاعدة البيانات
def init_db():
    try:
        conn = sqlite3.connect('clinic.db')
        c = conn.cursor()
        
        # جدول العيادات (التي تمثل الأطباء)
        c.execute('''CREATE TABLE IF NOT EXISTS clinics
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      doctor_name TEXT NOT NULL,
                      specialty TEXT NOT NULL,
                      phone TEXT,
                      email TEXT,
                      address TEXT,
                      working_hours TEXT,
                      telegram_bot_token TEXT,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # جدول المستخدمين (للعيادات والإدارة)
        c.execute('''CREATE TABLE IF NOT EXISTS users
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      username TEXT UNIQUE NOT NULL,
                      password TEXT NOT NULL,
                      role TEXT NOT NULL,
                      clinic_id INTEGER,
                      FOREIGN KEY (clinic_id) REFERENCES clinics (id))''')
        
        # جدول المواعيد (معدل)
        c.execute('''CREATE TABLE IF NOT EXISTS appointments
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      patient_name TEXT NOT NULL,
                      patient_phone TEXT NOT NULL,
                      clinic_id INTEGER NOT NULL,
                      appointment_date TEXT NOT NULL,
                      appointment_time TEXT NOT NULL,
                      status TEXT DEFAULT 'pending',
                      notes TEXT,
                      telegram_chat_id TEXT,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY (clinic_id) REFERENCES clinics (id))''')
        
        # محاولة إضافة الأعمدة الجديدة إذا لم تكن موجودة
        try:
            c.execute("ALTER TABLE appointments ADD COLUMN notes TEXT")
        except sqlite3.OperationalError:
            pass
            
        try:
            c.execute("ALTER TABLE appointments ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        except sqlite3.OperationalError:
            pass
            
        try:
            c.execute("ALTER TABLE appointments ADD COLUMN clinic_id INTEGER")
        except sqlite3.OperationalError:
            pass
        
        # إضافة بيانات تجريبية
        c.execute("SELECT COUNT(*) FROM clinics")
        if c.fetchone()[0] == 0:
            c.execute("INSERT INTO clinics (doctor_name, specialty, phone, email, address, working_hours) VALUES ('د. أحمد محمد', 'طب عام', '0551234567', 'ahmed@clinic.com', 'شارع الملك فهد، الرياض', 'من السبت إلى الخميس - 9 صباحاً إلى 5 مساءً')")
            c.execute("INSERT INTO clinics (doctor_name, specialty, phone, email, address, working_hours) VALUES ('د. سارة خالد', 'أسنان', '0551234568', 'sara@clinic.com', 'شارع العليا، الرياض', 'من الأحد إلى الخميس - 10 صباحاً إلى 6 مساءً')")
            
        c.execute("SELECT COUNT(*) FROM users")
        if c.fetchone()[0] == 0:
            c.execute("INSERT INTO users (username, password, role, clinic_id) VALUES ('admin', 'admin123', 'admin', NULL)")
            c.execute("INSERT INTO users (username, password, role, clinic_id) VALUES ('ahmed', 'ahmed123', 'clinic', 1)")
            c.execute("INSERT INTO users (username, password, role, clinic_id) VALUES ('sara', 'sara123', 'clinic', 2)")
        
        conn.commit()
        conn.close()
        logging.info("✅ تم تهيئة قاعدة البيانات بنجاح")
    except Exception as e:
        logging.error(f"❌ خطأ في تهيئة قاعدة البيانات: {e}")

init_db()

# مسارات التطبيق الرئيسية
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = sqlite3.connect('clinic.db')
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
        user = c.fetchone()
        conn.close()
        
        if user:
            session['user_id'] = user[0]
            session['username'] = user[1]
            session['role'] = user[3]
            session['clinic_id'] = user[4] if user[4] else None
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error='اسم المستخدم أو كلمة المرور غير صحيحة')
    
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('clinic.db')
    c = conn.cursor()
    
    user_role = session.get('role')
    clinic_id = session.get('clinic_id')
    
    # بناء الاستعلام بناءً على دور المستخدم
    if user_role == 'admin':
        # الإداري يرى جميع الإحصائيات
        c.execute("SELECT COUNT(*) FROM appointments")
        total_appointments = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM appointments WHERE status = 'pending'")
        pending_appointments = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM appointments WHERE status = 'confirmed'")
        confirmed_appointments = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM appointments WHERE status = 'cancelled'")
        cancelled_appointments = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM clinics")
        total_clinics = c.fetchone()[0]
        
        # آخر الحجوزات
        c.execute('''SELECT a.id, a.patient_name, a.patient_phone, c.doctor_name, a.appointment_date, a.appointment_time, a.status
                     FROM appointments a
                     JOIN clinics c ON a.clinic_id = c.id
                     ORDER BY a.id DESC LIMIT 10''')
        recent_appointments = c.fetchall()
        
    else:
        # العيادة ترى إحصائياتها فقط
        c.execute("SELECT COUNT(*) FROM appointments WHERE clinic_id = ?", (clinic_id,))
        total_appointments = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM appointments WHERE clinic_id = ? AND status = 'pending'", (clinic_id,))
        pending_appointments = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM appointments WHERE clinic_id = ? AND status = 'confirmed'", (clinic_id,))
        confirmed_appointments = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM appointments WHERE clinic_id = ? AND status = 'cancelled'", (clinic_id,))
        cancelled_appointments = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM clinics WHERE id = ?", (clinic_id,))
        total_clinics = c.fetchone()[0]
        
        # آخر الحجوزات للعيادة
        c.execute('''SELECT a.id, a.patient_name, a.patient_phone, c.doctor_name, a.appointment_date, a.appointment_time, a.status
                     FROM appointments a
                     JOIN clinics c ON a.clinic_id = c.id
                     WHERE a.clinic_id = ?
                     ORDER BY a.id DESC LIMIT 10''', (clinic_id,))
        recent_appointments = c.fetchall()
    
    conn.close()
    
    return render_template('dashboard.html', 
                          total_appointments=total_appointments,
                          pending_appointments=pending_appointments,
                          confirmed_appointments=confirmed_appointments,
                          cancelled_appointments=cancelled_appointments,
                          total_clinics=total_clinics,
                          recent_appointments=recent_appointments,
                          active_page='dashboard')

@app.route('/appointments')
def appointments_management():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    status_filter = request.args.get('status', 'all')
    user_role = session.get('role')
    clinic_id = session.get('clinic_id')
    
    conn = sqlite3.connect('clinic.db')
    c = conn.cursor()
    
    if user_role == 'admin':
        # الإداري يرى جميع الحجوزات
        if status_filter == 'all':
            c.execute('''SELECT a.id, a.patient_name, a.patient_phone, c.doctor_name, 
                        a.appointment_date, a.appointment_time, a.status, a.notes, a.created_at
                        FROM appointments a
                        JOIN clinics c ON a.clinic_id = c.id
                        ORDER BY a.appointment_date DESC, a.appointment_time DESC''')
        else:
            c.execute('''SELECT a.id, a.patient_name, a.patient_phone, c.doctor_name, 
                        a.appointment_date, a.appointment_time, a.status, a.notes, a.created_at
                        FROM appointments a
                        JOIN clinics c ON a.clinic_id = c.id
                        WHERE a.status = ?
                        ORDER BY a.appointment_date DESC, a.appointment_time DESC''', (status_filter,))
    else:
        # العيادة ترى حجوزاتها فقط
        if status_filter == 'all':
            c.execute('''SELECT a.id, a.patient_name, a.patient_phone, c.doctor_name, 
                        a.appointment_date, a.appointment_time, a.status, a.notes, a.created_at
                        FROM appointments a
                        JOIN clinics c ON a.clinic_id = c.id
                        WHERE a.clinic_id = ?
                        ORDER BY a.appointment_date DESC, a.appointment_time DESC''', (clinic_id,))
        else:
            c.execute('''SELECT a.id, a.patient_name, a.patient_phone, c.doctor_name, 
                        a.appointment_date, a.appointment_time, a.status, a.notes, a.created_at
                        FROM appointments a
                        JOIN clinics c ON a.clinic_id = c.id
                        WHERE a.clinic_id = ? AND a.status = ?
                        ORDER BY a.appointment_date DESC, a.appointment_time DESC''', (clinic_id, status_filter))
    
    appointments = c.fetchall()
    
    # إحصائيات الحجوزات
    if user_role == 'admin':
        c.execute("SELECT status, COUNT(*) FROM appointments GROUP BY status")
    else:
        c.execute("SELECT status, COUNT(*) FROM appointments WHERE clinic_id = ? GROUP BY status", (clinic_id,))
    
    status_stats = c.fetchall()
    
    conn.close()
    
    return render_template('appointments.html', 
                         appointments=appointments,
                         status_filter=status_filter,
                         status_stats=status_stats,
                         active_page='appointments')

@app.route('/clinics')
def clinics_management():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('dashboard'))
    
    conn = sqlite3.connect('clinic.db')
    c = conn.cursor()
    
    c.execute("SELECT * FROM clinics ORDER BY doctor_name")
    clinics = c.fetchall()
    
    # إحصائيات العيادات
    c.execute('''SELECT c.doctor_name, COUNT(a.id) as appointment_count 
                 FROM clinics c 
                 LEFT JOIN appointments a ON c.id = a.clinic_id 
                 GROUP BY c.id, c.doctor_name''')
    clinic_stats = c.fetchall()
    
    conn.close()
    
    return render_template('clinics.html', 
                         clinics=clinics, 
                         clinic_stats=clinic_stats,
                         active_page='clinics')

@app.route('/reports')
def reports():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('clinic.db')
    c = conn.cursor()
    
    user_role = session.get('role')
    clinic_id = session.get('clinic_id')
    
    # إحصائيات عامة
    if user_role == 'admin':
        c.execute("SELECT COUNT(*) FROM appointments")
        total_appointments = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM appointments WHERE status = 'confirmed'")
        confirmed_appointments = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM appointments WHERE status = 'pending'")
        pending_appointments = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM appointments WHERE status = 'cancelled'")
        cancelled_appointments = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM clinics")
        total_clinics = c.fetchone()[0]
        
        # الحجوزات حسب الشهر
        c.execute('''SELECT strftime('%Y-%m', appointment_date) as month, 
                     COUNT(*) as count 
                     FROM appointments 
                     GROUP BY month 
                     ORDER BY month DESC LIMIT 6''')
        monthly_stats = c.fetchall()
        
        # العيادات الأكثر حجوزات
        c.execute('''SELECT c.doctor_name, COUNT(a.id) as appointment_count 
                     FROM clinics c 
                     LEFT JOIN appointments a ON c.id = a.clinic_id 
                     GROUP BY c.id, c.doctor_name 
                     ORDER BY appointment_count DESC''')
        top_clinics = c.fetchall()
        
    else:
        # إحصائيات العيادة فقط
        c.execute("SELECT COUNT(*) FROM appointments WHERE clinic_id = ?", (clinic_id,))
        total_appointments = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM appointments WHERE clinic_id = ? AND status = 'confirmed'", (clinic_id,))
        confirmed_appointments = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM appointments WHERE clinic_id = ? AND status = 'pending'", (clinic_id,))
        pending_appointments = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM appointments WHERE clinic_id = ? AND status = 'cancelled'", (clinic_id,))
        cancelled_appointments = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM clinics WHERE id = ?", (clinic_id,))
        total_clinics = c.fetchone()[0]
        
        # الحجوزات حسب الشهر للعيادة
        c.execute('''SELECT strftime('%Y-%m', appointment_date) as month, 
                     COUNT(*) as count 
                     FROM appointments 
                     WHERE clinic_id = ?
                     GROUP BY month 
                     ORDER BY month DESC LIMIT 6''', (clinic_id,))
        monthly_stats = c.fetchall()
        
        # العيادة الحالية فقط
        c.execute('''SELECT c.doctor_name, COUNT(a.id) as appointment_count 
                     FROM clinics c 
                     LEFT JOIN appointments a ON c.id = a.clinic_id 
                     WHERE c.id = ?
                     GROUP BY c.id, c.doctor_name''', (clinic_id,))
        top_clinics = c.fetchall()
    
    conn.close()
    
    return render_template('reports.html',
                         total_appointments=total_appointments,
                         confirmed_appointments=confirmed_appointments,
                         pending_appointments=pending_appointments,
                         cancelled_appointments=cancelled_appointments,
                         total_clinics=total_clinics,
                         monthly_stats=monthly_stats,
                         top_clinics=top_clinics,
                         active_page='reports')

@app.route('/settings')
def settings():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # جلب معلومات العيادة إذا كان المستخدم عيادة
    clinic_info = None
    if session.get('role') == 'clinic':
        conn = sqlite3.connect('clinic.db')
        c = conn.cursor()
        c.execute("SELECT * FROM clinics WHERE id = ?", (session.get('clinic_id'),))
        clinic_info = c.fetchone()
        conn.close()
    
    return render_template('settings.html', active_page='settings', clinic_info=clinic_info)

# APIs
@app.route('/api/clinics')
def get_clinics():
    conn = sqlite3.connect('clinic.db')
    c = conn.cursor()
    c.execute("SELECT id, doctor_name, specialty FROM clinics")
    clinics = [{'id': row[0], 'name': row[1], 'specialty': row[2]} for row in c.fetchall()]
    conn.close()
    return jsonify(clinics)

@app.route('/api/appointments', methods=['GET', 'POST'])
def handle_appointments():
    if request.method == 'POST':
        data = request.json
        patient_name = data.get('patient_name')
        patient_phone = data.get('patient_phone')
        clinic_id = data.get('clinic_id')
        appointment_date = data.get('appointment_date')
        appointment_time = data.get('appointment_time')
        notes = data.get('notes', '')
        
        # إذا كان المستخدم عيادة، نستخدم clinic_id من الجلسة
        if session.get('role') == 'clinic' and not clinic_id:
            clinic_id = session.get('clinic_id')
        
        conn = sqlite3.connect('clinic.db')
        c = conn.cursor()
        c.execute('''INSERT INTO appointments 
                    (patient_name, patient_phone, clinic_id, appointment_date, appointment_time, notes)
                    VALUES (?, ?, ?, ?, ?, ?)''',
                 (patient_name, patient_phone, clinic_id, appointment_date, appointment_time, notes))
        appointment_id = c.lastrowid
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'appointment_id': appointment_id})
    
    else:
        # GET request - للحصول على الحجوزات
        user_role = session.get('role')
        clinic_id = session.get('clinic_id')
        
        conn = sqlite3.connect('clinic.db')
        c = conn.cursor()
        
        if user_role == 'admin':
            c.execute('''SELECT a.id, a.patient_name, a.patient_phone, c.doctor_name, 
                        a.appointment_date, a.appointment_time, a.status, a.notes
                        FROM appointments a
                        JOIN clinics c ON a.clinic_id = c.id''')
        else:
            c.execute('''SELECT a.id, a.patient_name, a.patient_phone, c.doctor_name, 
                        a.appointment_date, a.appointment_time, a.status, a.notes
                        FROM appointments a
                        JOIN clinics c ON a.clinic_id = c.id
                        WHERE a.clinic_id = ?''', (clinic_id,))
        
        appointments = []
        for row in c.fetchall():
            appointments.append({
                'id': row[0],
                'patient_name': row[1],
                'patient_phone': row[2],
                'clinic_name': row[3],
                'appointment_date': row[4],
                'appointment_time': row[5],
                'status': row[6],
                'notes': row[7]
            })
        conn.close()
        return jsonify(appointments)

@app.route('/api/appointments/<int:appointment_id>', methods=['PUT', 'DELETE'])
def handle_appointment(appointment_id):
    if request.method == 'PUT':
        data = request.json
        status = data.get('status')
        notes = data.get('notes', '')
        
        conn = sqlite3.connect('clinic.db')
        c = conn.cursor()
        if notes:
            c.execute("UPDATE appointments SET status = ?, notes = ? WHERE id = ?", (status, notes, appointment_id))
        else:
            c.execute("UPDATE appointments SET status = ? WHERE id = ?", (status, appointment_id))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
    
    elif request.method == 'DELETE':
        conn = sqlite3.connect('clinic.db')
        c = conn.cursor()
        c.execute("DELETE FROM appointments WHERE id = ?", (appointment_id,))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})

@app.route('/api/clinics', methods=['POST'])
def add_clinic():
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'غير مصرح'})
    
    data = request.json
    doctor_name = data.get('doctor_name')
    specialty = data.get('specialty')
    phone = data.get('phone', '')
    email = data.get('email', '')
    address = data.get('address', '')
    working_hours = data.get('working_hours', '')
    username = data.get('username')
    password = data.get('password')
    
    conn = sqlite3.connect('clinic.db')
    c = conn.cursor()
    
    try:
        # إضافة العيادة
        c.execute('''INSERT INTO clinics 
                    (doctor_name, specialty, phone, email, address, working_hours)
                    VALUES (?, ?, ?, ?, ?, ?)''',
                 (doctor_name, specialty, phone, email, address, working_hours))
        clinic_id = c.lastrowid
        
        # إضافة مستخدم للعيادة
        c.execute('''INSERT INTO users (username, password, role, clinic_id)
                    VALUES (?, ?, 'clinic', ?)''',
                 (username, password, clinic_id))
        
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'clinic_id': clinic_id})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/clinics/<int:clinic_id>', methods=['PUT', 'DELETE'])
def handle_clinic(clinic_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'غير مصرح'})
    
    if request.method == 'PUT':
        data = request.json
        doctor_name = data.get('doctor_name')
        specialty = data.get('specialty')
        phone = data.get('phone', '')
        email = data.get('email', '')
        address = data.get('address', '')
        working_hours = data.get('working_hours', '')
        
        conn = sqlite3.connect('clinic.db')
        c = conn.cursor()
        c.execute('''UPDATE clinics SET doctor_name = ?, specialty = ?, phone = ?, email = ?, address = ?, working_hours = ?
                    WHERE id = ?''', (doctor_name, specialty, phone, email, address, working_hours, clinic_id))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
    
    elif request.method == 'DELETE':
        conn = sqlite3.connect('clinic.db')
        c = conn.cursor()
        
        # حذف المستخدم المرتبط بالعيادة أولاً
        c.execute("DELETE FROM users WHERE clinic_id = ?", (clinic_id,))
        # حذف الحجوزات المرتبطة بالعيادة
        c.execute("DELETE FROM appointments WHERE clinic_id = ?", (clinic_id,))
        # حذف العيادة
        c.execute("DELETE FROM clinics WHERE id = ?", (clinic_id,))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

def start_bot_safely():
    """تشغيل البوت بطريقة آمنة مع التعامل مع الأخطاء"""
    try:
        from telebot_handler import run_bot
        logging.info("🚀 محاولة تشغيل روبوت تيليجرام...")
        
        # الانتظار قليلاً قبل البدء
        time.sleep(2)
        
        bot_thread = threading.Thread(target=run_bot)
        bot_thread.daemon = True
        bot_thread.start()
        logging.info("✅ تم بدء خيط البوت بنجاح")
        
    except Exception as e:
        logging.error(f"❌ فشل في تشغيل البوت: {e}")
        logging.info("⚠️  التطبيق سيعمل بدون البوت - الواجهة الأمامية فقط")

if __name__ == '__main__':
    # تشغيل البوت في خيط منفصل
    start_bot_safely()
    
    # تشغيل تطبيق Flask
    app.run(debug=True, use_reloader=False)