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

# 2. Fetch the payments

payments = gc_client.payments.all()

# 3. Format the data to match your Supabase table
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
            # Safely grab the mandate if it exists
            "mandate": getattr(p.links, 'mandate', None) if getattr(p, 'links', None) else None,
            # Payments do not have a direct customer link in GoCardless
            "customer": None 
        })
# 4. Push to Supabase
if records_to_insert:
    # Upsert updates the row if the ID already exists, or inserts it if it's new
    supabase.table("Payments").upsert(records_to_insert).execute()
    print(f"Successfully synced {len(records_to_insert)} payments.")

# 5. Fetch Mandates
mandates = gc_client.mandates.all()
mandates_to_insert = []

for m in mandates:
    mandates_to_insert.append({
        "id": m.id,
        "created_at": m.created_at,
        "reference": m.reference,
        "status": m.status,
        # Mandates DO have a direct link to the customer
        "customer": getattr(m.links, 'customer', None) if getattr(m, 'links', None) else None
    })

# 6. Push Mandates to Supabase
if mandates_to_insert:
    supabase.table("Mandates").upsert(mandates_to_insert).execute()
    print(f"Successfully synced {len(mandates_to_insert)} mandates.")

# 7. Fetch Customers
customers = gc_client.customers.all()
customers_to_insert = []

for c in customers:
    customers_to_insert.append({
        "id": c.id,
        "created_at": c.created_at,
        "email": c.email,
        "given_name": c.given_name,
        "family_name": c.family_name,
        "company_name": c.company_name,
        "phone_number": c.phone_number
    })

# 8. Push Customers to Supabase
if customers_to_insert:
    supabase.table("Customers").upsert(customers_to_insert).execute()
    print(f"Successfully synced {len(customers_to_insert)} customers.")
