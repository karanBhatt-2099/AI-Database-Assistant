"""Create schema, load SYNTHETIC data and create the SELECT-only role.
Run once with an admin URL:  python -m db.seed
"""
import os, random, datetime as dt
from pathlib import Path
import psycopg
from psycopg import sql

random.seed(42)
REGIONS = ["North America", "Europe", "Asia Pacific", "Latin America", "Middle East & Africa"]
CATS = {
    "Electronics": ["Wireless Earbuds", "4K Monitor", "Mechanical Keyboard", "Smart Speaker", "Webcam HD"],
    "Home": ["Air Purifier", "Robot Vacuum", "Coffee Maker", "Desk Lamp", "Bedside Clock"],
    "Fitness": ["Yoga Mat", "Smart Watch", "Resistance Bands", "Water Bottle", "Foam Roller"],
    "Office": ["Standing Desk", "Ergo Chair", "Notebook Pack", "Pen Set", "Monitor Arm"],
    "Outdoors": ["Day Backpack", "Camping Stove", "Trail Shoes", "Headlamp", "Rain Jacket"],
}
FIRST = ["Aarav", "Maya", "Liam", "Sofia", "Noah", "Zara", "Ethan", "Lena", "Omar", "Chloe", "Ravi", "Anya", "Diego", "Mei", "Jonas"]
LAST = ["Shah", "Garcia", "Kim", "Novak", "Silva", "Khan", "Meyer", "Tanaka", "Okafor", "Rossi", "Patel", "Smith"]
REGION_WEIGHT = [0.30, 0.28, 0.22, 0.10, 0.10]


def main():
    admin = os.environ["ADMIN_DATABASE_URL"]
    pw = os.environ["READONLY_PASSWORD"]
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(Path(__file__).with_name("schema.sql").read_text())
        with conn.cursor() as cur:
            with cur.copy("COPY regions (name) FROM STDIN") as cp:
                for r in REGIONS: cp.write_row((r,))
            prices = []
            with cur.copy("COPY products (name, category, unit_price) FROM STDIN") as cp:
                for cat, names in CATS.items():
                    for n in names:
                        price = round(random.uniform(9, 450), 2)
                        prices.append(price); cp.write_row((n, cat, price))
            custs = []
            with cur.copy("COPY customers (name, email, region_id, signup_date) FROM STDIN") as cp:
                for i in range(1, 401):
                    rid = random.choices(range(1, 6), REGION_WEIGHT)[0]
                    sd = dt.date(2023, 7, 1) + dt.timedelta(days=random.randint(0, 540))
                    custs.append(sd)
                    cp.write_row((f"{random.choice(FIRST)} {random.choice(LAST)}", f"user{i}@example.com", rid, sd))
            orders, items = [], []
            for oid in range(1, 6001):
                cid = random.randint(1, 400)
                start = max(custs[cid - 1], dt.date(2024, 1, 1))
                d = start + dt.timedelta(days=random.randint(0, max(1, (dt.date(2025, 12, 31) - start).days)))
                status = random.choices(["completed", "cancelled", "refunded"], [0.86, 0.08, 0.06])[0]
                orders.append((cid, d, status))
                for p in random.sample(range(1, 26), random.randint(1, 4)):
                    items.append((oid, p, random.randint(1, 5), prices[p - 1]))
            with cur.copy("COPY orders (customer_id, order_date, status) FROM STDIN") as cp:
                for row in orders: cp.write_row(row)
            with cur.copy("COPY order_items (order_id, product_id, quantity, unit_price) FROM STDIN") as cp:
                for row in items: cp.write_row(row)
        # ---- SELECT-only role ----
        exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname='readonly_user'").fetchone()
        verb = "ALTER" if exists else "CREATE"
        conn.execute(sql.SQL(verb + " ROLE readonly_user LOGIN PASSWORD {}").format(sql.Literal(pw)))
        dbn = conn.execute("SELECT current_database()").fetchone()[0]
        for stmt in [
            sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(dbn)),
            sql.SQL("GRANT CONNECT ON DATABASE {} TO readonly_user").format(sql.Identifier(dbn)),
            sql.SQL("REVOKE CREATE ON SCHEMA public FROM PUBLIC"),
            sql.SQL("GRANT USAGE ON SCHEMA public TO readonly_user"),
            sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly_user"),
            sql.SQL("ALTER ROLE readonly_user SET default_transaction_read_only = on"),
            sql.SQL("ALTER ROLE readonly_user SET statement_timeout = '5s'"),
        ]:
            conn.execute(stmt)
    print("Seeded: 5 regions, 25 products, 400 customers, 6000 orders. Role readonly_user ready.")


if __name__ == "__main__":
    main()
