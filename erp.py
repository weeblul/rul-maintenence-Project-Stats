#Layer 4: ERP system stored in a SQLite database (erp.db). All other files read and write the database only through this file
import os
import sqlite3
from datetime import datetime

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "erp.db")

def connect():
    #open the database file (SQLite creates it if it doesn't exist)
    return sqlite3.connect(DB_FILE)


def get_database_status():
    if not os.path.exists(DB_FILE):
        return {"connected": False, "initialized": False, "predictions": 0}

    conn = connect()
    try:
        tables = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        required_tables = {
            "inventory", "suppliers", "purchase_requisitions", "work_orders",
            "predictions", "audit_log", "invoices", "model_predictions",
        }
        initialized = required_tables.issubset(tables)
        prediction_count = 0
        if "model_predictions" in tables:
            prediction_count = conn.execute(
                "SELECT COUNT(*) FROM model_predictions"
            ).fetchone()[0]
        return {
            "connected": True,
            "initialized": initialized,
            "predictions": prediction_count,
        }
    finally:
        conn.close()


def create_database():
    conn = connect()
    #cursor sends sql commands to the db
    cur = conn.cursor()

    #1. delete old table if it exists
    #(model_predictions is NOT deleted here, it comes from the notebook, see save_model_predictions)
    for table in["inventory", "suppliers", "purchase_requisitions", "work_orders", "predictions", "audit_log", "invoices"]:
        cur.execute("DROP TABLE IF EXISTS "+ table)

    #2. create the empty tables.
    #inventory: which part, its name, and how many we hold
    cur.execute("CREATE TABLE inventory (part_id TEXT, part_name TEXT, quantity INTEGER)")
    #suppliers: who they are and which part they sell
    cur.execute("CREATE TABLE suppliers (supplier_id TEXT, name TEXT, part_id TEXT, unit_price REAL, lead_time_days INTEGER)")
    #pr_id is numbered automatically. Shows when it was raised, for what part, from whom. Total price and approved or waiting for approval
    cur.execute("CREATE TABLE purchase_requisitions (pr_id INTEGER PRIMARY KEY AUTOINCREMENT, day INTEGER, engine TEXT, part_id TEXT, supplier_id TEXT, quantity INTEGER, total_cost REAL, status TEXT)")
    #work orders, which engine, the job, priority, wo_id incremented automatically.
    cur.execute("CREATE TABLE work_orders (wo_id INTEGER PRIMARY KEY AUTOINCREMENT, engine TEXT, description TEXT, priority TEXT, status TEXT, scheduled_day INTEGER)")
    #predictions: the model's RUL and risk for one engine on one day
    cur.execute("CREATE TABLE predictions (day INTEGER, engine TEXT, rul REAL, risk REAL)")
    #audit log: logging when, who did it, what they did, and why
    cur.execute("CREATE TABLE audit_log (log_id INTEGER PRIMARY KEY AUTOINCREMENT, day INTEGER, agent TEXT, action TEXT, reason TEXT)")
    #invoices: one bill from a supplier for an approved requisition. Starts as 'pending', a reviewer changes it to 'posted'
    cur.execute("CREATE TABLE invoices (invoice_id INTEGER PRIMARY KEY AUTOINCREMENT, pr_id INTEGER, supplier_id TEXT, "
                "engine TEXT, part_id TEXT, quantity INTEGER, amount REAL, status TEXT, created_day INTEGER, posted_at TEXT)")
    #model_predictions: the notebook's predictions for the 200 test engines (used by the dashboard table)
    cur.execute("CREATE TABLE IF NOT EXISTS model_predictions (engine TEXT, actual_rul REAL, tree_pred REAL, linear_pred REAL)")

    #3. Starting data
    #spare parts: only 3 spare HPC modules, so later engines need new ones ordered
    cur.execute("INSERT INTO inventory VALUES ('HPC-01', 'High pressure compressor module', 3)")

    #two suppliers for the same parts (made-up prices in euro)
    cur.execute("INSERT INTO suppliers VALUES ('SUP-A', 'AeroParts Ltd', 'HPC-01', 42000, 21)")
    cur.execute("INSERT INTO suppliers VALUES ('SUP-B', 'JetSpare Co', 'HPC-01', 55000, 4)")

    #some routine low-priority jobs already planned
    for i in range(1,7):
        cur.execute("INSERT INTO work_orders (engine, description, priority, status, scheduled_day) "
                    "VALUES (?, ?, ?, ?, ?)",
                    #FD001_ + str(i*10) generates engine IDs
                    #scheduled day: 50 + i * 20, spaces jobs out every 20 days
                    ("FD001_" + str(i * 10), "Routine inspection", "low", "open", 50 + i * 20))
    
    #save the change
    conn.commit()
    conn.close()

#inventory functions
#getter function for getting quantity of a particular part
def get_stock(part_id):
    conn = connect()
    #ask for the quantity of one part, and fill the ? placeholder with part_id, as a tuple
    row = conn.execute("SELECT quantity FROM inventory WHERE part_id = ?", (part_id,)).fetchone()

    conn.close()
    #if no stock recorded in inventory, return 0, otherwise return the row with part info
    if row is None:
        return 0
    return row[0]
#getter function for reserving a part for repair
def reserve_part(part_id):
    #if there is no parts to take, state that to the user
    if get_stock(part_id) < 1:
        raise ValueError("No " + part_id + " left in stock")

    conn = connect()
    #decrease quantity when we retrieve the part. 
    conn.execute("UPDATE inventory SET quantity = quantity - 1 WHERE part_id = ?", (part_id,))
    #save changes
    conn.commit()
    conn.close()

#supplier and purchase functions
#Find all suppliers for the part and return them sorted by price, lowest first. 
def get_suppliers(part_id):
    conn = connect()
    #select attributes from supplier where part_id fills the ? placeholder value. 
    #Then order by unit_price
    rows = conn.execute("SELECT supplier_id, name, unit_price, lead_time_days "
                        "FROM suppliers WHERE part_id = ? "
                        "ORDER BY unit_price",
                        (part_id,)).fetchall()
    conn.close()
    return rows

#once procurement has chose a supplier, it records the decision as a purchas requisition, a formal request to buy
def add_requisition(day, engine, part_id, supplier_id, quantity, total_cost, status):
    conn = connect()
    cur = conn.execute("INSERT INTO purchase_requisitions (day, engine, part_id, supplier_id, "
                       "quantity, total_cost, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (day, engine, part_id, supplier_id, quantity, total_cost, status))
    conn.commit()
    #the pr_id SQLite just gave this row
    new_id = cur.lastrowid
    conn.close()

    #an approved requisition means we buy the part, so the supplier sends us an invoice
    if status == "approved":
        create_invoice(new_id)
    return new_id

#this function picks out the rows whose status is "waiting for approval". 
def get_pending_requisitions():
    conn = connect()
    #select from teh db entries which are not yet approved
    rows = conn.execute("SELECT pr_id, day, engine, part_id, supplier_id, total_cost "
                        "FROM purchase_requisitions "
                        "WHERE status= 'waiting for approval'").fetchall()
    conn.close()
    return rows

#A person clicks Approve, so that requisition status turns to approved
def approve_requisition(pr_id):
    conn = connect()
    #change the status to approved, and fill the ? with the requisition number. 
    cur = conn.execute("UPDATE purchase_requisitions SET status = 'approved' "
                       "WHERE pr_id = ? AND status = 'waiting for approval'",
                       (pr_id,))
    conn.commit()
    #how many rows the update changed
    changed = cur.rowcount
    conn.close()

    if changed == 0:
        raise ValueError("PR " + str(pr_id) + " is not waiting for approval")

    #now that a person approved it, the supplier sends an invoice
    return create_invoice(pr_id)

#work order functions
#book a maintenance job on the calendar. Every new job starts as "open"
def add_work_order(engine, description, priority, scheduled_day):
    conn = connect()
    #wo_id is left out (SQLite numbers it), staus is written straight in as "open"
    cur = conn.execute("INSERT INTO work_orders (engine, description, priority, status, scheduled_day) "
                       "VALUES (?, ?, ?, 'open', ?)",
                       (engine, description, priority, scheduled_day))
    conn.commit()
    #the wo_id SQLite gave this job
    new_id = cur.lastrowid
    conn.close()
    return new_id

#find routine jobs the scheduler is allowed to move: low priority, still open, inside the day window
def get_open_low_priority_orders(day_from, day_to):
    conn = connect()
    #three conditions joined witht AND. Between includes both end days. Sorted so the earliest job comes first
    rows = conn.execute("SELECT wo_id, engine, scheduled_day FROM work_orders "
                        "WHERE priority = 'low' AND status = 'open' "
                        "AND scheduled_day BETWEEN ? AND ? "
                        "ORDER BY scheduled_day",
                        (day_from, day_to)).fetchall()
    conn.close()
    return rows

#move a routine job later. The erp itself refuses to move anything that isn't low priority and open
def defer_work_order(wo_id, new_day):
    conn = connect()
    #set the new day and mar it deferred, but only for low-priotiy and open jobs
    cur = conn.execute("UPDATE work_orders SET status = 'deferred', scheduled_day = ? "
                       "WHERE wo_id = ? AND priority = 'low' AND status = 'open'",
                       (new_day, wo_id))
    conn.commit()
    changed = cur.rowcount
    conn.close()
    #mptjomg cjamged: wrong number, high priority, or already deferred
    if changed == 0:
        raise ValueError("Work order "+ str(wo_id) + " can't be deferred")

#predictions and audit log
#store the model's output for one engine on one day (the dashboard charts are built from these rows)
def save_prediction(day, engine, rul, risk):
    conn = connect()
    conn.execute("INSERT INTO predictions VALUES (?, ?, ?, ?)", (day, engine, rul, risk))
    conn.commit()
    conn.close()

#record one action, when ti happened, who did it, what they did, and why
def add_log(day, agent, action, reason):
    conn = connect()
    #log_id is left out, SQLite numbers it
    conn.execute("INSERT INTO audit_log (day, agent, action, reason) VALUES (?, ?, ?, ?)",
                 (day, agent, action, reason))
    conn.commit()
    conn.close()

#used by dashboard
#table names cant go into ? placeholder. So the name is glued to sql string, which means anything passed in becomes part of the command.
def read_table(table_name):
    TABLES = ["inventory", "suppliers", "purchase_requisitions", "work_orders", "predictions", "audit_log",
              "invoices", "model_predictions"]
    
    #table name cant go in a ? placeholder, so check it against the allow-list before using it
    if table_name not in TABLES:
        raise ValueError("Unknown tables: "+ table_name)

    import pandas as pd
    conn = connect()
    #run the query and turn the result into a data frame in one step
    df = pd.read_sql_query("SELECT * FROM " + table_name, conn)
    conn.close()
    return df


#invoice functions
#an invoice is made for every approved purchase requisition. It starts as "pending"
def create_invoice(pr_id):
    conn = connect()
    #look up the requisition so the invoice copies its details
    pr = conn.execute("SELECT day, engine, part_id, supplier_id, quantity, total_cost "
                      "FROM purchase_requisitions WHERE pr_id = ?", (pr_id,)).fetchone()
    if pr is None:
        conn.close()
        raise ValueError("PR " + str(pr_id) + " does not exist")

    day, engine, part_id, supplier_id, quantity, total_cost = pr
    cur = conn.execute("INSERT INTO invoices (pr_id, supplier_id, engine, part_id, quantity, amount, status, created_day) "
                       "VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)",
                       (pr_id, supplier_id, engine, part_id, quantity, total_cost, day))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()

    add_log(day, "ERP", "Invoice " + str(new_id) + " received for PR " + str(pr_id),
            "The requisition was approved, so the supplier invoice waits for a reviewer")
    return new_id

#small helper: run a SELECT and give back a list of dictionaries (column name -> value), easy to send to the dashboard
def select_as_dicts(sql, values=()):
    conn = connect()
    #row_factory makes every row behave like a dictionary
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, values).fetchall()
    conn.close()
    result = []
    for row in rows:
        result.append(dict(row))
    return result

#the invoice columns plus the supplier name (JOIN finds the supplier row with the same supplier_id)
INVOICE_SQL = ("SELECT invoices.*, suppliers.name AS supplier_name FROM invoices "
               "JOIN suppliers ON invoices.supplier_id = suppliers.supplier_id "
               "AND invoices.part_id = suppliers.part_id ")

def get_pending_invoices():
    return select_as_dicts(INVOICE_SQL + "WHERE invoices.status = 'pending' ORDER BY invoices.invoice_id")

def get_posted_invoices():
    return select_as_dicts(INVOICE_SQL + "WHERE invoices.status = 'posted' ORDER BY invoices.invoice_id")

#one invoice (or None if the number does not exist)
def get_invoice(invoice_id):
    rows = select_as_dicts(INVOICE_SQL + "WHERE invoices.invoice_id = ?", (invoice_id,))
    if len(rows) == 0:
        return None
    return rows[0]

#the reviewer approves a pending invoice, so it is posted (booked) in the ERP
def approve_invoice(invoice_id):
    posted_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn = connect()
    #only change it if it is still pending, so the same invoice can't be posted twice
    cur = conn.execute("UPDATE invoices SET status = 'posted', posted_at = ? "
                       "WHERE invoice_id = ? AND status = 'pending'", (posted_at, invoice_id))
    conn.commit()
    changed = cur.rowcount
    conn.close()

    if changed == 0:
        raise ValueError("Invoice " + str(invoice_id) + " is not pending")

    invoice = get_invoice(invoice_id)
    add_log(invoice["created_day"], "Reviewer", "Posted invoice " + str(invoice_id),
            "Reviewer approved the invoice for " + invoice["engine"] + " (" + str(invoice["amount"]) + " euro)")

#save the notebook's test predictions (one row per test engine)
def save_model_predictions(engines, actual, tree_pred, linear_pred):
    conn = connect()
    conn.execute("CREATE TABLE IF NOT EXISTS model_predictions (engine TEXT, actual_rul REAL, tree_pred REAL, linear_pred REAL)")
    #remove the old rows so running the notebook twice does not add duplicates
    conn.execute("DELETE FROM model_predictions")
    for i in range(len(engines)):
        conn.execute("INSERT INTO model_predictions VALUES (?, ?, ?, ?)",
                     (str(engines[i]), round(float(actual[i]), 1), round(float(tree_pred[i]), 1), round(float(linear_pred[i]), 1)))
    conn.commit()
    conn.close()

#used by the dashboard table: [engine, actual RUL, tree prediction, linear prediction]
def get_model_predictions():
    conn = connect()
    rows = conn.execute("SELECT engine, actual_rul, tree_pred, linear_pred FROM model_predictions").fetchall()
    conn.close()
    result = []
    for row in rows:
        result.append(list(row))
    return result

#requisitions that wait for a person, with the supplier name (for the dashboard)
def get_pending_requisitions_with_names():
    return select_as_dicts("SELECT purchase_requisitions.*, suppliers.name AS supplier_name FROM purchase_requisitions "
                           "JOIN suppliers ON purchase_requisitions.supplier_id = suppliers.supplier_id "
                           "AND purchase_requisitions.part_id = suppliers.part_id "
                           "WHERE purchase_requisitions.status = 'waiting for approval' ORDER BY pr_id")
