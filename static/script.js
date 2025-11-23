// دالة لتحميل العيادات في select
async function loadClinics() {
    try {
        const response = await fetch('/api/clinics');
        const clinics = await response.json();
        
        const select = document.getElementById('clinic_id');
        if (select) {
            select.innerHTML = '<option value="">اختر العيادة</option>';
            
            clinics.forEach(function(clinic) {
                const option = document.createElement('option');
                option.value = clinic.id;
                option.textContent = clinic.name + ' - ' + clinic.specialty;
                select.appendChild(option);
            });
        }
    } catch (error) {
        console.error('Error loading clinics:', error);
        alert('❌ حدث خطأ في تحميل قائمة العيادات');
    }
}

// دالة لإضافة حجز جديد
async function addAppointment() {
    const form = document.getElementById('addAppointmentForm');
    const formData = new FormData(form);
    
    // التحقق من الحقول المطلوبة
    const patientName = formData.get('patient_name');
    const patientPhone = formData.get('patient_phone');
    const appointmentDate = formData.get('appointment_date');
    const appointmentTime = formData.get('appointment_time');
    
    if (!patientName || !patientPhone || !appointmentDate || !appointmentTime) {
        alert('❌ الرجاء ملء جميع الحقول المطلوبة');
        return;
    }
    
    // إذا كان المستخدم مسؤولاً، نتحقق من اختيار العيادة
    let clinicId;
    const clinicSelect = document.getElementById('clinic_id');
    if (clinicSelect) {
        clinicId = formData.get('clinic_id');
        if (!clinicId) {
            alert('❌ الرجاء اختيار العيادة');
            return;
        }
    } else {
        // إذا كان مستخدم عيادة، نستخدم clinic_id الخاص به من الجلسة
        clinicId = document.body.getAttribute('data-clinic-id');
    }
    
    const appointmentData = {
        patient_name: patientName,
        patient_phone: patientPhone,
        clinic_id: clinicId,
        appointment_date: appointmentDate,
        appointment_time: appointmentTime,
        notes: formData.get('notes')
    };
    
    try {
        const response = await fetch('/api/appointments', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(appointmentData)
        });
        
        const result = await response.json();
        
        if (result.success) {
            alert('✅ تم إضافة الحجز بنجاح');
            closeAddAppointmentModal();
            location.reload();
        } else {
            alert('❌ حدث خطأ أثناء إضافة الحجز');
        }
    } catch (error) {
        console.error('Error adding appointment:', error);
        alert('❌ حدث خطأ أثناء إضافة الحجز');
    }
}

// دالة لعرض modal إضافة حجز
function showAddAppointmentModal() {
    const userRole = document.body.getAttribute('data-user-role');
    
    if (userRole === 'admin') {
        loadClinics().then(() => {
            document.getElementById('addAppointmentModal').style.display = 'block';
        }).catch(error => {
            console.error('Error loading clinics:', error);
            document.getElementById('addAppointmentModal').style.display = 'block';
        });
    } else {
        document.getElementById('addAppointmentModal').style.display = 'block';
    }
    
    // تعيين تاريخ اليوم كحد أدنى
    const today = new Date().toISOString().split('T')[0];
    document.getElementById('appointment_date').min = today;
}

// دالة لإغلاق modal إضافة حجز
function closeAddAppointmentModal() {
    document.getElementById('addAppointmentModal').style.display = 'none';
    document.getElementById('addAppointmentForm').reset();
}