import sqlite3
import random
from datetime import datetime, timedelta

db = sqlite3.connect('garage.db')
cursor = db.cursor()

# Get spare parts
cursor.execute("SELECT id, price FROM spare_parts")
parts = cursor.fetchall()
if not parts:
    print("No spare parts found in the database. Please add spare parts.")
    db.close()
    exit()

# Get ALL repair orders
cursor.execute("SELECT id, created_at, status FROM repair_orders")
all_orders = cursor.fetchall()

# Ensure ALL repair orders have an invoice
for ro_id, created_at, status in all_orders:
    cursor.execute("SELECT id FROM invoices WHERE repair_order_id = ?", (ro_id,))
    inv = cursor.fetchone()
    
    if not inv:
        # Create an invoice for this repair order
        # We try to use a date slightly after created_at
        try:
            ca_date = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
            inv_date = (ca_date + timedelta(hours=random.randint(1, 48))).strftime("%Y-%m-%d %H:%M:%S")
        except:
            inv_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
        inv_status = "Paid" if status == "Completed" else "Unpaid"
        cursor.execute("""
            INSERT INTO invoices (repair_order_id, status, created_at)
            VALUES (?, ?, ?)
        """, (ro_id, inv_status, inv_date))

# Fetch all orders and invoices now
cursor.execute("""
    SELECT r.id, i.id 
    FROM repair_orders r
    JOIN invoices i ON r.id = i.repair_order_id
""")
orders_with_invoices = cursor.fetchall()

# Delete ALL existing repair order parts to avoid duplication or orphans
cursor.execute("DELETE FROM repair_order_parts")

print(f"Populating details for {len(orders_with_invoices)} orders...")

for order_id, invoice_id in orders_with_invoices:
    # Pick a random number of parts (1 to 6)
    num_parts = random.randint(1, 6)
    chosen_parts = random.sample(parts, min(num_parts, len(parts)))
    
    parts_total = 0
    
    for part_id, price in chosen_parts:
        quantity = random.randint(1, 4)
        # Randomize price if price is 0
        unit_price = price if price > 0 else random.randint(15, 250) * 10000
        
        cursor.execute("""
            INSERT INTO repair_order_parts (repair_order_id, part_id, quantity, unit_price)
            VALUES (?, ?, ?, ?)
        """, (order_id, part_id, quantity, unit_price))
        
        parts_total += (quantity * unit_price)
        
    # Generate service cost (Công sửa chữa/bảo dưỡng)
    service_cost = random.randint(20, 200) * 15000 # ~300k to 3m
    
    # Update repair order estimated cost (used in template as service cost fallback)
    cursor.execute("UPDATE repair_orders SET estimated_cost = ? WHERE id = ?", (service_cost, order_id))
    
    # Update invoice totals
    subtotal = parts_total + service_cost
    vat = subtotal * 0.1
    discount = 0
    if random.random() > 0.75:
        discount = random.choice([50000, 100000, 200000, 500000])
        
    total = subtotal + vat - discount
    
    cursor.execute("""
        UPDATE invoices
        SET subtotal = ?, vat_amount = ?, discount = ?, total_amount = ?
        WHERE id = ?
    """, (subtotal, vat, discount, total, invoice_id))

db.commit()
db.close()

print(f"Successfully created invoices and fully detailed parts for all {len(orders_with_invoices)} repair orders in the system!")
