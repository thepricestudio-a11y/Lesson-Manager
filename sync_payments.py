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

# Change this to a dictionary to enforce unique Supabase IDs
customers_to_update = {} 
customers_to_insert = []

# Emails of departing customers to explicitly ignore (from our earlier fix)
ignored_emails = ["claireuphill@me.com"]

for c in customers:
    gc_email = c.email.lower() if c.email else ""
    
    if gc_email in ignored_emails:
        continue
    
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
        # By using the sb_id as the dictionary key, any duplicate emails 
        # will simply overwrite the previous entry instead of stacking up
        customers_to_update[sb_id] = record 
    else:
        customers_to_insert.append(record)

# Convert the dictionary values back into a list for Supabase
update_list = list(customers_to_update.values())

if update_list:
    supabase.table("customers").upsert(update_list).execute()
    print(f"Successfully updated {len(update_list)} existing customers.")

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
# ==========================================
# STEP 4: PROCESS NIGHTLY PAYG LESSONS
# ==========================================
print("Starting PAYG sweep...")

# 1. Fetch lessons flagged for PAYG that haven't been requested yet
unprocessed_payg = supabase.table("lessons").select("id, pupil_id, lesson_fee").eq("payg", True).is_("payg_status", "null").execute().data

if unprocessed_payg:
    # 2. Build lookup dictionaries to find the correct Mandate for each Pupil
    pupils = supabase.table("pupils").select("pupil_id, customer").execute().data
    pupil_to_customer = {p['pupil_id']: p['customer'] for p in pupils}
    
    # Fetch active mandates from GoCardless directly (ensures we use the active GC ID, not the Supabase UUID)
    active_mandates = supabase.table("mandates").select("id, customer").eq("status", "active").execute().data
    customer_to_mandate = {m['customer']: m['id'] for m in active_mandates}

    for lesson in unprocessed_payg:
        customer_uuid = pupil_to_customer.get(lesson['pupil_id'])
        gc_mandate_id = customer_to_mandate.get(customer_uuid)
        fee = lesson.get('lesson_fee')

        if gc_mandate_id and fee and float(fee) > 0:
            try:
                # 3. Create the payment via GoCardless API
                payment = gc_client.payments.create(
                    params={
                        "amount": int(float(fee) * 100), # Convert to minor units (pence)
                        "currency": "GBP",
                        "links": {"mandate": gc_mandate_id},
                        "description": "Lesson PAYG Charge"
                    }
                )
                
                # 4. Update the lesson row in Supabase with the success status
                supabase.table("lessons").update({
                    "payg_status": "Requested",
                    "payg_id": payment.id
                }).eq("id", lesson['id']).execute()
                
                print(f"Success: Charged £{fee} for Lesson {lesson['id']} (Payment ID: {payment.id})")
                
            except Exception as e:
                # Log the error straight into the database so you can see it on the frontend
                error_msg = str(e)[:250] # Truncate to fit column limits
                supabase.table("lessons").update({
                    "payg_status": f"Error: {error_msg}"
                }).eq("id", lesson['id']).execute()
                print(f"Failed to process PAYG for lesson {lesson['id']}: {e}")
        else:
            print(f"Skipped Lesson {lesson['id']}: Missing active mandate or zero fee.")
else:
    print("No new PAYG lessons to process.")
