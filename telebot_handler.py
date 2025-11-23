import telebot
import sqlite3
import json
from datetime import datetime, timedelta
import os
import logging

# إعداد التسجيل
logging.basicConfig(level=logging.INFO)

# سيتم إدارة التوكنات من قاعدة البيانات
BOT_TOKEN = '8345802723:AAEvsYf8cHL7ddpRdLlR51-9l2uJmn2ICps'  # الرمز الافتراضي

try:
    bot = telebot.TeleBot(BOT_TOKEN)
    logging.info("✅ تم تهيئة روبوت تيليجرام بنجاح")
except Exception as e:
    logging.error(f"❌ خطأ في تهيئة البوت: {e}")
    class MockBot:
        def set_webhook(self, *args, **kwargs): pass
        def remove_webhook(self, *args, **kwargs): pass
    bot = MockBot()

# حالات المستخدمين
user_states = {}

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    try:
        user_states[message.chat.id] = {'step': 'main_menu'}
        
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        item1 = telebot.types.KeyboardButton('📅 حجز موعد')
        item2 = telebot.types.KeyboardButton('📋 مواعيدي')
        item3 = telebot.types.KeyboardButton('💊 العيادات المتاحة')
        item4 = telebot.types.KeyboardButton('📞 اتصل بنا')
        markup.add(item1, item2, item3, item4)
        
        bot.send_message(message.chat.id, 
                        "مرحباً بك في نظام حجز المواعيد الطبية! 🤖\n"
                        "اختر الخيار المناسب:", 
                        reply_markup=markup)
        logging.info(f"📨 تم إرسال رسالة ترحيب للمستخدم {message.chat.id}")
    except Exception as e:
        logging.error(f"❌ خطأ في send_welcome: {e}")

@bot.message_handler(func=lambda message: message.text == '💊 العيادات المتاحة')
def show_clinics(message):
    try:
        conn = sqlite3.connect('clinic.db')
        c = conn.cursor()
        c.execute("SELECT doctor_name, specialty, phone, working_hours FROM clinics")
        clinics = c.fetchall()
        conn.close()
        
        if clinics:
            response = "💊 العيادات المتاحة:\n\n"
            for clinic in clinics:
                response += f"👨‍⚕️ الطبيب: {clinic[0]}\n"
                response += f"📋 التخصص: {clinic[1]}\n"
                response += f"📞 الهاتف: {clinic[2] or 'غير متوفر'}\n"
                response += f"⏰ أوقات العمل: {clinic[3] or 'غير محدد'}\n"
                response += "─" * 20 + "\n\n"
        else:
            response = "لا توجد عيادات مسجلة حالياً."
        
        bot.send_message(message.chat.id, response)
        
    except Exception as e:
        logging.error(f"❌ خطأ في show_clinics: {e}")
        bot.send_message(message.chat.id, "❌ حدث خطأ في عرض العيادات. الرجاء المحاولة لاحقاً.")

@bot.message_handler(func=lambda message: message.text == '📅 حجز موعد')
def book_appointment(message):
    try:
        user_states[message.chat.id] = {'step': 'select_clinic'}
        
        # الحصول على قائمة العيادات
        conn = sqlite3.connect('clinic.db')
        c = conn.cursor()
        c.execute("SELECT id, doctor_name, specialty FROM clinics")
        clinics = c.fetchall()
        conn.close()
        
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        for clinic in clinics:
            markup.add(telebot.types.KeyboardButton(f"{clinic[1]} - {clinic[2]}"))
        markup.add(telebot.types.KeyboardButton('🔙 رجوع'))
        
        clinic_list = "\n".join([f"• {clinic[1]} - {clinic[2]}" for clinic in clinics])
        bot.send_message(message.chat.id, f"اختر العيادة من القائمة:\n\n{clinic_list}", reply_markup=markup)
        logging.info(f"📝 بدء حجز موعد للمستخدم {message.chat.id}")
    except Exception as e:
        logging.error(f"❌ خطأ في book_appointment: {e}")

@bot.message_handler(func=lambda message: user_states.get(message.chat.id, {}).get('step') == 'select_clinic')
def select_clinic(message):
    try:
        if message.text == '🔙 رجوع':
            send_welcome(message)
            return
        
        # استخراج معرف العيادة من النص
        clinic_name = message.text.split(' - ')[0]
        
        conn = sqlite3.connect('clinic.db')
        c = conn.cursor()
        c.execute("SELECT id, doctor_name FROM clinics WHERE doctor_name = ?", (clinic_name,))
        clinic = c.fetchone()
        conn.close()
        
        if clinic:
            user_states[message.chat.id]['clinic_id'] = clinic[0]
            user_states[message.chat.id]['clinic_name'] = clinic[1]
            user_states[message.chat.id]['step'] = 'get_patient_name'
            
            bot.send_message(message.chat.id, "رجاءً أدخل اسمك الكامل:")
        else:
            bot.send_message(message.chat.id, "العيادة غير موجودة، رجاءً اختر عيادة من القائمة:")
    except Exception as e:
        logging.error(f"❌ خطأ في select_clinic: {e}")

@bot.message_handler(func=lambda message: user_states.get(message.chat.id, {}).get('step') == 'get_patient_name')
def get_patient_name(message):
    try:
        user_states[message.chat.id]['patient_name'] = message.text
        user_states[message.chat.id]['step'] = 'get_patient_phone'
        bot.send_message(message.chat.id, "رجاءً أدخل رقم هاتفك:")
    except Exception as e:
        logging.error(f"❌ خطأ في get_patient_name: {e}")

@bot.message_handler(func=lambda message: user_states.get(message.chat.id, {}).get('step') == 'get_patient_phone')
def get_patient_phone(message):
    try:
        user_states[message.chat.id]['patient_phone'] = message.text
        user_states[message.chat.id]['step'] = 'select_date'
        
        # عرض تواريخ الأسبوع القادم
        dates = []
        for i in range(1, 8):
            date = (datetime.now() + timedelta(days=i)).strftime('%Y-%m-%d')
            day_name = get_arabic_day_name((datetime.now() + timedelta(days=i)).weekday())
            dates.append((date, day_name))
        
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        for date, day_name in dates:
            markup.add(telebot.types.KeyboardButton(f"{date} ({day_name})"))
        markup.add(telebot.types.KeyboardButton('🔙 رجوع'))
        
        dates_text = "\n".join([f"• {date} ({day})" for date, day in dates])
        bot.send_message(message.chat.id, f"اختر التاريخ من القائمة:\n\n{dates_text}", reply_markup=markup)
    except Exception as e:
        logging.error(f"❌ خطأ في get_patient_phone: {e}")

def get_arabic_day_name(day_index):
    """ترجمة أسماء الأيام إلى العربية"""
    days = {
        0: 'الإثنين',
        1: 'الثلاثاء',
        2: 'الأربعاء',
        3: 'الخميس',
        4: 'الجمعة',
        5: 'السبت',
        6: 'الأحد'
    }
    return days.get(day_index, '')

@bot.message_handler(func=lambda message: user_states.get(message.chat.id, {}).get('step') == 'select_date')
def select_date(message):
    try:
        if message.text == '🔙 رجوع':
            book_appointment(message)
            return
        
        # استخراج التاريخ من النص
        selected_date = message.text.split(' ')[0]
        user_states[message.chat.id]['appointment_date'] = selected_date
        user_states[message.chat.id]['step'] = 'select_time'
        
        # عرض الأوقات المتاحة
        times = [
            ('09:00', '9:00 صباحاً'),
            ('10:00', '10:00 صباحاً'),
            ('11:00', '11:00 صباحاً'),
            ('12:00', '12:00 ظهراً'),
            ('13:00', '1:00 مساءً'),
            ('14:00', '2:00 مساءً'),
            ('15:00', '3:00 مساءً'),
            ('16:00', '4:00 مساءً')
        ]
        
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        for time_code, time_display in times:
            markup.add(telebot.types.KeyboardButton(time_display))
        markup.add(telebot.types.KeyboardButton('🔙 رجوع'))
        
        times_text = "\n".join([f"• {time_display}" for time_code, time_display in times])
        bot.send_message(message.chat.id, f"اختر الوقت من القائمة:\n\n{times_text}", reply_markup=markup)
    except Exception as e:
        logging.error(f"❌ خطأ في select_date: {e}")

@bot.message_handler(func=lambda message: user_states.get(message.chat.id, {}).get('step') == 'select_time')
def select_time(message):
    try:
        if message.text == '🔙 رجوع':
            get_patient_phone(message)
            return
        
        # تحويل الوقت إلى تنسيق 24 ساعة
        time_mapping = {
            '9:00 صباحاً': '09:00',
            '10:00 صباحاً': '10:00',
            '11:00 صباحاً': '11:00',
            '12:00 ظهراً': '12:00',
            '1:00 مساءً': '13:00',
            '2:00 مساءً': '14:00',
            '3:00 مساءً': '15:00',
            '4:00 مساءً': '16:00'
        }
        
        selected_time = time_mapping.get(message.text, message.text)
        user_states[message.chat.id]['appointment_time'] = selected_time
        user_states[message.chat.id]['appointment_time_display'] = message.text
        
        # عرض تأكيد الحجز
        confirmation_message = (
            f"📋 تأكيد بيانات الحجز:\n\n"
            f"👤 الاسم: {user_states[message.chat.id]['patient_name']}\n"
            f"📞 الهاتف: {user_states[message.chat.id]['patient_phone']}\n"
            f"💊 العيادة: {user_states[message.chat.id]['clinic_name']}\n"
            f"📅 التاريخ: {user_states[message.chat.id]['appointment_date']}\n"
            f"⏰ الوقت: {message.text}\n\n"
            f"هل تريد تأكيد الحجز؟"
        )
        
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(telebot.types.KeyboardButton('✅ نعم، تأكيد الحجز'))
        markup.add(telebot.types.KeyboardButton('❌ لا، إلغاء الحجز'))
        
        bot.send_message(message.chat.id, confirmation_message, reply_markup=markup)
        user_states[message.chat.id]['step'] = 'confirm_booking'
        
    except Exception as e:
        logging.error(f"❌ خطأ في select_time: {e}")
        bot.send_message(message.chat.id, "❌ حدث خطأ في اختيار الوقت. الرجاء المحاولة مرة أخرى.")

@bot.message_handler(func=lambda message: user_states.get(message.chat.id, {}).get('step') == 'confirm_booking')
def confirm_booking(message):
    try:
        if message.text == '✅ نعم، تأكيد الحجز':
            # حفظ الحجز في قاعدة البيانات
            conn = sqlite3.connect('clinic.db')
            c = conn.cursor()
            c.execute('''INSERT INTO appointments 
                        (patient_name, patient_phone, clinic_id, appointment_date, appointment_time, telegram_chat_id, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?)''',
                     (user_states[message.chat.id]['patient_name'],
                      user_states[message.chat.id]['patient_phone'],
                      user_states[message.chat.id]['clinic_id'],
                      user_states[message.chat.id]['appointment_date'],
                      user_states[message.chat.id]['appointment_time'],
                      message.chat.id,
                      'pending'))
            appointment_id = c.lastrowid
            conn.commit()
            conn.close()
            
            # إرسال تأكيد الحجز
            confirmation_message = (
                f"✅ تم حجز الموعد بنجاح!\n\n"
                f"📋 تفاصيل الحجز:\n"
                f"🆔 رقم الحجز: #{appointment_id}\n"
                f"👤 الاسم: {user_states[message.chat.id]['patient_name']}\n"
                f"📞 الهاتف: {user_states[message.chat.id]['patient_phone']}\n"
                f"💊 العيادة: {user_states[message.chat.id]['clinic_name']}\n"
                f"📅 التاريخ: {user_states[message.chat.id]['appointment_date']}\n"
                f"⏰ الوقت: {user_states[message.chat.id]['appointment_time_display']}\n"
                f"📊 الحالة: ⏳ قيد الانتظار\n\n"
                f"سيتم تأكيد الحجز من قبل الإدارة قريباً.\n"
                f"للاستفسار: 0112345678"
            )
            
            bot.send_message(message.chat.id, confirmation_message)
            logging.info(f"✅ تم إنشاء حجز جديد رقم {appointment_id} للمستخدم {message.chat.id}")
            
        elif message.text == '❌ لا، إلغاء الحجز':
            bot.send_message(message.chat.id, "❌ تم إلغاء عملية الحجز.")
        
        # العودة للقائمة الرئيسية
        user_states[message.chat.id] = {'step': 'main_menu'}
        send_welcome(message)
        
    except Exception as e:
        logging.error(f"❌ خطأ في confirm_booking: {e}")
        bot.send_message(message.chat.id, "❌ حدث خطأ أثناء حفظ الحجز. الرجاء المحاولة مرة أخرى.")

@bot.message_handler(func=lambda message: message.text == '📋 مواعيدي')
def my_appointments(message):
    try:
        conn = sqlite3.connect('clinic.db')
        c = conn.cursor()
        c.execute('''SELECT a.id, a.patient_name, c.doctor_name, a.appointment_date, a.appointment_time, a.status
                     FROM appointments a
                     JOIN clinics c ON a.clinic_id = c.id
                     WHERE a.telegram_chat_id = ? 
                     ORDER BY a.appointment_date DESC, a.appointment_time DESC''', (message.chat.id,))
        appointments = c.fetchall()
        conn.close()
        
        if appointments:
            response = "📋 مواعيدك:\n\n"
            for app in appointments:
                status_emoji = "⏳" if app[5] == 'pending' else "✅" if app[5] == 'confirmed' else "❌"
                status_text = "قيد الانتظار" if app[5] == 'pending' else "مؤكد" if app[5] == 'confirmed' else "ملغى"
                
                # تحويل الوقت إلى تنسيق مقروء
                time_obj = datetime.strptime(app[4], '%H:%M')
                time_display = time_obj.strftime('%I:%M %p').replace('AM', 'صباحاً').replace('PM', 'مساءً')
                
                response += f"{status_emoji} الحجز #{app[0]}\n"
                response += f"👤 الاسم: {app[1]}\n"
                response += f"💊 العيادة: {app[2]}\n"
                response += f"📅 التاريخ: {app[3]}\n"
                response += f"⏰ الوقت: {time_display}\n"
                response += f"📊 الحالة: {status_text}\n\n"
                response += "─" * 20 + "\n\n"
        else:
            response = "لا توجد مواعيد مسجلة لديك.\n\nيمكنك حجز موعد جديد باستخدام زر '📅 حجز موعد'"
        
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(telebot.types.KeyboardButton('📅 حجز موعد جديد'))
        markup.add(telebot.types.KeyboardButton('🔙 القائمة الرئيسية'))
        
        bot.send_message(message.chat.id, response, reply_markup=markup)
        
    except Exception as e:
        logging.error(f"❌ خطأ في my_appointments: {e}")
        bot.send_message(message.chat.id, "❌ حدث خطأ في عرض المواعيد. الرجاء المحاولة لاحقاً.")

@bot.message_handler(func=lambda message: message.text == '📞 اتصل بنا')
def contact_us(message):
    try:
        contact_info = (
            "📞 قنوات الاتصال:\n\n"
            "📞 الهاتف:\n"
            "0112345678\n"
            "0501234567\n\n"
            "📧 البريد الإلكتروني:\n"
            "info@clinic.com\n"
            "support@clinic.com\n\n"
            "📍 العنوان:\n"
            "شارع الملك فهد، الرياض\n"
            "المملكة العربية السعودية\n\n"
            "⏰ أوقات الاستقبال:\n"
            "من السبت إلى الخميس\n"
            "9:00 ص - 5:00 م"
        )
        
        # إضافة زر للاتصال السريع
        markup = telebot.types.InlineKeyboardMarkup()
        call_button = telebot.types.InlineKeyboardButton(text="📞 اتصل الآن", url="tel:+966112345678")
        location_button = telebot.types.InlineKeyboardButton(text="📍 الموقع", url="https://maps.google.com/?q=الرياض,شارع+الملك+فهد")
        markup.add(call_button, location_button)
        
        bot.send_message(message.chat.id, contact_info, reply_markup=markup)
        
    except Exception as e:
        logging.error(f"❌ خطأ في contact_us: {e}")

@bot.message_handler(func=lambda message: message.text in ['📅 حجز موعد جديد', '🔙 القائمة الرئيسية'])
def handle_navigation(message):
    """معالجة أزرار التنقل"""
    send_welcome(message)

@bot.message_handler(func=lambda message: True)
def handle_other_messages(message):
    """معالجة أي رسائل أخرى"""
    try:
        # إذا كان المستخدم في حالة غير معروفة، نعيده للقائمة الرئيسية
        if message.chat.id in user_states:
            del user_states[message.chat.id]
        
        bot.send_message(message.chat.id, 
                        "لم أفهم طلبك. الرجاء استخدام الأزرار المتاحة أو إرسال /start للبدء من جديد.")
        send_welcome(message)
    except Exception as e:
        logging.error(f"❌ خطأ في handle_other_messages: {e}")

def setup_webhook():
    """إعداد Webhook للبوت"""
    try:
        # إزالة أي Webhook سابق
        bot.remove_webhook()
        
        # ضبط Webhook جديد (للاستخدام مع الخوادم الحقيقية)
        # bot.set_webhook(url=WEBHOOK_URL + '/webhook')
        
        logging.info("✅ تم إعداد Webhook (جاهز للاستخدام مع الخادم)")
    except Exception as e:
        logging.error(f"❌ خطأ في إعداد Webhook: {e}")

def run_bot_polling():
    """تشغيل البوت باستخدام Polling (للاختبار المحلي)"""
    try:
        logging.info("🚀 بدء تشغيل روبوت تيليجرام (Polling Mode)...")
        
        # إزالة أي Webhook سابق
        bot.remove_webhook()
        
        # استخدام Polling
        bot.polling(none_stop=True, interval=1, timeout=60)
    except Exception as e:
        logging.error(f"❌ حدث خطأ في روبوت تيليجرام: {e}")
        logging.info("🔄 إعادة المحاولة بعد 10 ثواني...")
        import time
        time.sleep(10)
        run_bot_polling()

def run_bot_webhook():
    """تشغيل البوت باستخدام Webhook"""
    try:
        logging.info("🚀 بدء تشغيل روبوت تيليجرام (Webhook Mode)...")
        setup_webhook()
    except Exception as e:
        logging.error(f"❌ خطأ في تشغيل Webhook: {e}")

def run_bot():
    """تشغيل البوت - اختيار الوضع المناسب"""
    # استخدام Polling للاختبار المحلي
    run_bot_polling()
    
    # أو استخدام Webhook للإنتاج
    # run_bot_webhook()

# دالة لمعالجة Webhook (للاستخدام مع Flask)
def handle_webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''
    return 'Invalid request', 400

# دالة مساعدة للحصول على الأطباء (للاستخدام من التطبيق الرئيسي)
def get_clinics_list():
    """الحصول على قائمة العيادات من قاعدة البيانات"""
    try:
        conn = sqlite3.connect('clinic.db')
        c = conn.cursor()
        c.execute("SELECT id, doctor_name, specialty FROM clinics")
        clinics = c.fetchall()
        conn.close()
        return clinics
    except Exception as e:
        logging.error(f"❌ خطأ في الحصول على قائمة العيادات: {e}")
        return []

# دالة لإرسال إشعارات للمستخدمين
def send_notification(chat_id, message):
    """إرسال إشعار للمستخدم عبر التليجرام"""
    try:
        bot.send_message(chat_id, message)
        return True
    except Exception as e:
        logging.error(f"❌ خطأ في إرسال الإشعار للمستخدم {chat_id}: {e}")
        return False