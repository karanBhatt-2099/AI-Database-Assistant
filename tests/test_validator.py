import pytest
from app.validator import validate, UnsafeQuery

GOOD = [
    "SELECT name FROM products",
    "SELECT p.name, SUM(oi.quantity*oi.unit_price) r FROM order_items oi JOIN products p USING(product_id) GROUP BY 1 ORDER BY 2 DESC LIMIT 5;",
    "WITH m AS (SELECT date_trunc('month', order_date) d FROM orders) SELECT d, COUNT(*) FROM m GROUP BY d",
    "SELECT name FROM products UNION SELECT name FROM regions",
    "SELECT * FROM public.customers",
]
BAD = [
    ("DROP TABLE orders", "Only SELECT"),
    ("DELETE FROM orders", "Only SELECT"),
    ("UPDATE products SET unit_price=0", "Only SELECT"),
    ("INSERT INTO regions(name) VALUES ('x')", "Only SELECT"),
    ("SELECT 1; DROP TABLE orders", "Exactly one"),
    ("SELECT * INTO newt FROM orders", "Forbidden"),
    ("SELECT * FROM orders FOR UPDATE", "Forbidden"),
    ("SELECT * FROM pg_shadow", "not in the allowed"),
    ("SELECT * FROM information_schema.tables", "not accessible"),
    ("SELECT pg_sleep(30)", "not allowed"),
    ("SELECT pg_read_file('/etc/passwd')", "not allowed"),
    ("SELECT set_config('default_transaction_read_only','off',false)", "not allowed"),
    ("SELECT * FROM orders -- hi", "comments"),
    ("", "Empty"),
    ("COPY orders TO '/tmp/x'", "Only SELECT"),
    ("SELEC nonsense (", "parse"),
]

@pytest.mark.parametrize("sql", GOOD)
def test_good(sql):
    out = validate(sql)
    assert out.startswith("SELECT * FROM (") and out.endswith("LIMIT 500")

@pytest.mark.parametrize("sql,why", BAD)
def test_bad(sql, why):
    with pytest.raises(UnsafeQuery) as e:
        validate(sql)
    assert why.lower() in str(e.value).lower()
