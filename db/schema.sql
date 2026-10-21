DROP TABLE IF EXISTS order_items, orders, products, customers, regions CASCADE;

CREATE TABLE regions   (region_id SERIAL PRIMARY KEY, name TEXT NOT NULL UNIQUE);
CREATE TABLE customers (customer_id SERIAL PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL,
                        region_id INT NOT NULL REFERENCES regions, signup_date DATE NOT NULL);
CREATE TABLE products  (product_id SERIAL PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL,
                        unit_price NUMERIC(10,2) NOT NULL);
CREATE TABLE orders    (order_id SERIAL PRIMARY KEY, customer_id INT NOT NULL REFERENCES customers,
                        order_date DATE NOT NULL,
                        status TEXT NOT NULL CHECK (status IN ('completed','cancelled','refunded')));
CREATE TABLE order_items (order_item_id SERIAL PRIMARY KEY, order_id INT NOT NULL REFERENCES orders,
                        product_id INT NOT NULL REFERENCES products,
                        quantity INT NOT NULL CHECK (quantity > 0),
                        unit_price NUMERIC(10,2) NOT NULL);

CREATE INDEX ON orders(order_date);
CREATE INDEX ON orders(customer_id);
CREATE INDEX ON order_items(order_id);
CREATE INDEX ON order_items(product_id);
