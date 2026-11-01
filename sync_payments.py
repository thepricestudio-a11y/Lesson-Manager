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
            # Left side matches your new Supabase columns
            # Right side still pulls from the GoCardless links object
            "mandate": p.links.mandate if getattr(p, 'links', None) else None,
            "customer": p.links.customer if getattr(p, 'links', None) else None
        })

# 4. Push to Supabase
if records_to_insert:
    # Upsert updates the row if the ID already exists, or inserts it if it's new
    supabase.table("Payments").upsert(records_to_insert).execute()
    print(f"Successfully synced {len(records_to_insert)} payments.")
