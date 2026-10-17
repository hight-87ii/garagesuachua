import sqlite3
import random

db = sqlite3.connect('garage.db')
cursor = db.cursor()

# 1. Update Customers
cursor.execute("SELECT id, username, full_name, phone, email, address, birth_date FROM users WHERE role = 'customer'")
users = cursor.fetchall()

addresses = [
    'Số 12 Nguyễn Trãi, Thanh Xuân, Hà Nội', 
    'Tòa nhà Landmark 81, Bình Thạnh, TP.HCM', 
    '45 Lê Lợi, Quận 1, TP.HCM', 
    '128 Cầu Giấy, Hà Nội', 
    '10 Trần Phú, Hà Đông, Hà Nội', 
    '50 Láng Hạ, Đống Đa, Hà Nội', 
    '99 Nguyễn Thị Minh Khai, Q3, TP.HCM', 
    '22/5 Hẻm X, Nguyễn Văn Cừ, Quận 5, TP.HCM'
]

contacts = ['phone', 'zalo', 'email']

for u in users:
    uid, uname, fname, phone, email, addr, bdate = u
    
    new_phone = phone
    if not phone or phone == '---' or len(phone) < 9:
        new_phone = '09' + str(random.randint(10000000, 99999999))
        
    new_email = email
    if not email or email == '---':
        name_part = (fname or uname or 'khachhang').lower().replace(' ', '').replace('đ', 'd').replace('á', 'a').replace('ị', 'i').replace('ả', 'a').replace('ó', 'o').replace('ồ', 'o')
        new_email = f'{name_part}{random.randint(10,99)}@gmail.com'
        
    new_addr = addr
    if not addr or addr == '---':
        new_addr = random.choice(addresses)
        
    new_bdate = bdate
    if not bdate:
        year = random.randint(1975, 2000)
        month = random.randint(1, 12)
        day = random.randint(1, 28)
        new_bdate = f'{year}-{month:02d}-{day:02d}'
        
    cursor.execute('''
        UPDATE users 
        SET phone = ?, email = ?, address = ?, birth_date = ?, preferred_contact = ? 
        WHERE id = ?
    ''', (new_phone, new_email, new_addr, new_bdate, random.choice(contacts), uid))

# 2. Update Vehicles
cursor.execute("SELECT id, make, model, vin FROM vehicles")
vehicles = cursor.fetchall()

colors = ['Trắng', 'Đen', 'Đỏ', 'Bạc', 'Xám', 'Xanh lam', 'Nâu']
fuel_types = ['Xăng', 'Dầu Diesel', 'Xăng lai điện (Hybrid)', 'Điện']

for v in vehicles:
    vid, make, model, current_vin = v
    year = random.randint(2015, 2024)
    color = random.choice(colors)
    fuel = random.choice(fuel_types)
    
    # Generate VIN: 17 chars if missing
    vin = current_vin
    if not vin or vin == '---':
        chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
        vin = ''.join(random.choice(chars) for _ in range(17))
        
    engine_no = 'ENG' + ''.join(random.choice('0123456789') for _ in range(8))
    
    cursor.execute('''
        UPDATE vehicles
        SET manufacture_year = ?, color = ?, fuel_type = ?, vin = ?, engine_number = ?
        WHERE id = ?
    ''', (year, color, fuel, vin, engine_no, vid))

# 3. Update Repair Orders ODO
cursor.execute("SELECT id, current_odo, final_odo FROM repair_orders")
orders = cursor.fetchall()
for o in orders:
    oid, cur_odo, fin_odo = o
    if not cur_odo:
        cur_odo = random.randint(15000, 85000)
    if not fin_odo:
        fin_odo = cur_odo + random.randint(2, 20)
        
    cursor.execute('''
        UPDATE repair_orders
        SET current_odo = ?, final_odo = ?
        WHERE id = ?
    ''', (cur_odo, fin_odo, oid))


db.commit()
db.close()
print('Successfully updated database with dummy user and vehicle data!')
