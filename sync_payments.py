import os
import gocardless_pro
from supabase import create_client, Client

# 1. Initialize connections using secure environment variables
gc_client = gocardless_pro.Client(
    access_token=os.environ['GOCARDLESS_TOKEN'], 
    environment='live' # change to 'sandbox' if testing
)
supabase: Client = create_client(
    os.environ['SUPABASE_URL'], 
    os.environ['SUPABASE_KEY']
)

# ==========================================
# STEP 1: SYNC CUSTOMERS (The Top Level)
# ==========================================
customers = gc_client.customers.all()
sb_customers_response = supabase.table("customers").select("id, email, gocardless_id").execute()
sb_customers = sb_customers_response.data

email_to_sb_id = {c['email'].lower(): c['id'] for c in sb_customers if c.get('email')}
gc_id_to_sb_id = {c['gocardless_id']: c['id'] for c in sb_customers if c.get('gocardless_id')}

customers_to_update = []
customers_to_insert = []

for c in customers:
    gc_email = c.email.lower() if c.email else ""
    
    if c.id in gc_id_to_sb_id:
        sb_id = gc_id_to_sb_id[c.id]
    elif gc_email in email_to_sb_id:
        sb_id = email_to_sb_id[gc_email]
    else:
        sb_id = None 

    record = {
        "gocardless_id": c.id,
        "email": c.email,
        "given_name": c.given_name,
        "family_name": c.family_name,
        "company_name": c.company_name,
        "phone_number": c.phone_number
    }
    
    if sb_id:
        record["id"] = sb_id
        customers_to_update.append(record) # Has an ID, goes to upsert
    else:
        customers_to_insert.append(record) # No ID, goes to insert

# Execute separately to prevent the SDK from padding missing IDs with nulls
if customers_to_update:
    supabase.table("customers").upsert(customers_to_update).execute()
    print(f"Successfully updated {len(customers_to_update)} existing customers.")

if customers_to_insert:
    supabase.table("customers").insert(customers_to_insert).execute()
    print(f"Successfully inserted {len(customers_to_insert)} new customers.")
# ==========================================
# STEP 2: SYNC MANDATES (Children of Customers)
# ==========================================
mandates = gc_client.mandates.all()

updated_sb_customers = supabase.table("customers").select("id, gocardless_id").execute().data
gc_id_to_uuid = {c['gocardless_id']: c['id'] for c in updated_sb_customers if c.get('gocardless_id')}

mandates_to_upsert = []
for m in mandates:
    gc_customer_id = getattr(m.links, 'customer', None) if getattr(m, 'links', None) else None
    sb_customer_uuid = gc_id_to_uuid.get(gc_customer_id) if gc_customer_id else None

    mandates_to_upsert.append({
        "id": m.id,
        "created_at": m.created_at,
        "reference": m.reference,
        "status": m.status,
        "customer": sb_customer_uuid 
    })

if mandates_to_upsert:
    supabase.table("mandates").upsert(mandates_to_upsert).execute()
    print(f"Successfully synced {len(mandates_to_upsert)} mandates.")

# ==========================================
# STEP 3: SYNC PAYMENTS (Children of Mandates)
# ==========================================
payments = gc_client.payments.all(
    params={
        "charge_date[gte]": "2026-08-01"
    }
)

records_to_insert = []
for p in payments:
    records_to_insert.append({
        "id": p.id,
        "created_at": p.created_at,
        "charge_date": p.charge_date,
        "amount": p.amount / 100.0,
        "description": p.description,
        "currency": p.currency,
        "status": p.status,
        "amount_refunded": (p.amount_refunded / 100.0) if p.amount_refunded else 0,
        "transaction_fee": None,
        "payout_date": None,
        "mandate": getattr(p.links, 'mandate', None) if getattr(p, 'links', None) else None,
        "customer": None 
    })

if records_to_insert:
    supabase.table("payments").upsert(records_to_insert).execute()
    print(f"Successfully synced {len(records_to_insert)} payments.")
