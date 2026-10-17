import sqlite3
import random

db = sqlite3.connect('garage.db')
cursor = db.cursor()

# Get spare parts to assign
cursor.execute("SELECT id, price FROM spare_parts")
parts = cursor.fetchall()

if not parts:
    print("No spare parts found in the database. Please make sure spare parts exist.")
    db.close()
    exit()

# Get all repair orders that have invoices
cursor.execute("""
    SELECT r.id, i.id 
    FROM repair_orders r
    JOIN invoices i ON r.id = i.repair_order_id
""")
orders_with_invoices = cursor.fetchall()

for order_id, invoice_id in orders_with_invoices:
    # Clear existing parts for this order to avoid duplicates while reseeding
    cursor.execute("DELETE FROM repair_order_parts WHERE repair_order_id = ?", (order_id,))
    
    # Pick a random number of parts (1 to 5)
    num_parts = random.randint(1, 5)
    chosen_parts = random.sample(parts, min(num_parts, len(parts)))
    
    parts_total = 0
    
    for part_id, price in chosen_parts:
        quantity = random.randint(1, 4)
        unit_price = price if price > 0 else random.randint(150000, 2500000)
        
        cursor.execute("""
            INSERT INTO repair_order_parts (repair_order_id, part_id, quantity, unit_price)
            VALUES (?, ?, ?, ?)
        """, (order_id, part_id, quantity, unit_price))
        
        parts_total += (quantity * unit_price)
        
    # Generate service cost
    service_cost = random.randint(300, 2500) * 1000 # 300k to 2.5m
    
    # Update repair order estimated cost (sometimes used as service cost)
    cursor.execute("UPDATE repair_orders SET estimated_cost = ? WHERE id = ?", (service_cost, order_id))
    
    # Update invoice totals
    subtotal = parts_total + service_cost
    vat = subtotal * 0.1
    discount = 0
    if random.random() > 0.7:
        discount = random.choice([50000, 100000, 200000])
        
    total = subtotal + vat - discount
    
    cursor.execute("""
        UPDATE invoices
        SET subtotal = ?, vat_amount = ?, discount = ?, total_amount = ?
        WHERE id = ?
    """, (subtotal, vat, discount, total, invoice_id))

db.commit()
db.close()

print(f"Successfully added parts and updated invoices for {len(orders_with_invoices)} repair orders!")
