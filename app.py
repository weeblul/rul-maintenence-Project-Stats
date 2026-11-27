# Layer 5: a small Flask web server for the dashboard.
# The browser can't open erp.db by itself, so this server reads the ERP (through erp.py)
# and sends the data to dashboard.html.
#
# Start it with:  python app.py   then open http://localhost:5000
# (In Colab the last cell of the notebook starts it and gives you a link.)

import os
import sqlite3
from flask import Flask, jsonify, send_file, render_template_string
import erp

app = Flask(__name__)
HERE = os.path.dirname(os.path.abspath(__file__))


# the dashboard page
@app.route("/")
def home():
    return send_file(os.path.join(HERE, "dashboard.html"))


@app.route("/api/status")
def database_status():
    return jsonify(erp.get_database_status())


# the 200 test engines: [engine, actual RUL, tree prediction, linear prediction]
@app.route("/api/engines")
def engines():
    if not erp.get_database_status()["initialized"]:
        return jsonify({"error": "ERP database is not initialized. Run the notebook first."}), 503
    try:
        return jsonify(erp.get_model_predictions())
    except sqlite3.OperationalError:
        return jsonify({"error": "ERP database is not initialized. Run the notebook first."}), 503


# pending and posted invoices
@app.route("/api/invoices")
def invoices():
    if not erp.get_database_status()["initialized"]:
        return jsonify({"error": "ERP database is not initialized. Run the notebook first."}), 503
    try:
        return jsonify({"pending": erp.get_pending_invoices(), "posted": erp.get_posted_invoices()})
    except sqlite3.OperationalError:
        # the tables are not there yet
        return jsonify({"error": "No ERP data yet. Run the notebook first."}), 503


# the reviewer clicks "Approve and post"
@app.route("/api/invoices/<int:invoice_id>/approve", methods=["POST"])
def approve_invoice(invoice_id):
    try:
        erp.approve_invoice(invoice_id)
    except ValueError as error:
        return jsonify({"ok": False, "error": str(error)}), 400
    return jsonify({"ok": True, "invoice_id": invoice_id})


# requisitions over the cost limit that wait for a person
@app.route("/api/requisitions")
def requisitions():
    if not erp.get_database_status()["initialized"]:
        return jsonify({"error": "ERP database is not initialized. Run the notebook first."}), 503
    try:
        return jsonify(erp.get_pending_requisitions_with_names())
    except sqlite3.OperationalError:
        return jsonify({"error": "No ERP data yet. Run the notebook first."}), 503


# a person approves a requisition -> the ERP creates a pending invoice for it
@app.route("/api/requisitions/<int:pr_id>/approve", methods=["POST"])
def approve_requisition(pr_id):
    try:
        invoice_id = erp.approve_requisition(pr_id)
    except ValueError as error:
        return jsonify({"ok": False, "error": str(error)}), 400
    day = erp.get_invoice(invoice_id)["created_day"]
    erp.add_log(day, "Person", "Approved PR " + str(pr_id), "Approved in the dashboard")
    return jsonify({"ok": True, "invoice_id": invoice_id})


# the printable invoice (only for posted invoices)
INVOICE_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Invoice {{ inv.invoice_id }}</title>
  <style>
    @page { size: A4; margin: 18mm; }
    body { font: 14px system-ui, sans-serif; color: #142038; background: #f4f6fa; margin: 0; }
    .sheet { background: white; width: 210mm; min-height: 297mm; margin: 20px auto; padding: 18mm;
             box-sizing: border-box; box-shadow: 0 2px 10px rgba(0,0,0,.1); }
    h1 { margin: 0; font-size: 30px; }
    .top { display: flex; justify-content: space-between; border-bottom: 2px solid #101d33;
           padding-bottom: 12px; margin-bottom: 24px; }
    table { width: 100%; border-collapse: collapse; margin: 24px 0; }
    th, td { text-align: left; padding: 10px 8px; border-bottom: 1px solid #e7ebf1; }
    th { background: #eef2f8; }
    .total { text-align: right; font-size: 18px; font-weight: 700; }
    .status { display: inline-block; padding: 4px 10px; border-radius: 20px; background: #e3f6e8; color: #17672e; }
    .note { color: #536178; font-size: 12px; margin-top: 40px; }
    .buttons { text-align: center; margin: 16px; }
    button, a.back { font: inherit; padding: 8px 14px; border: 1px solid #cbd5e2; border-radius: 8px;
                     background: white; cursor: pointer; color: inherit; text-decoration: none; }
    @media print {
      body { background: white; }
      .sheet { margin: 0; box-shadow: none; width: auto; min-height: auto; padding: 0; }
      .buttons { display: none; }
    }
  </style>
</head>
<body>
  <div class="buttons">
    <button onclick="window.print()">Print / save as PDF</button>
    <a class="back" href="../">Back to dashboard</a>
  </div>

  <div class="sheet">
    <div class="top">
      <div>
        <h1>INVOICE</h1>
        <div>No. INV-{{ "%04d" % inv.invoice_id }}</div>
      </div>
      <div style="text-align:right">
        <strong>{{ inv.supplier_name }}</strong><br>
        Supplier ID: {{ inv.supplier_id }}
      </div>
    </div>

    <p><strong>Bill to:</strong> Fleet Maintenance (demo ERP)</p>
    <p>
      Purchase requisition: PR {{ inv.pr_id }}<br>
      Invoice raised: simulation day {{ inv.created_day }}<br>
      Posted: {{ inv.posted_at }}<br>
      Status: <span class="status">{{ inv.status }}</span>
    </p>

    <table>
      <tr><th>Part</th><th>For engine</th><th>Quantity</th><th>Amount (EUR)</th></tr>
      <tr>
        <td>{{ inv.part_id }} (High pressure compressor module)</td>
        <td>{{ inv.engine }}</td>
        <td>{{ inv.quantity }}</td>
        <td>{{ "{:,.2f}".format(inv.amount) }}</td>
      </tr>
    </table>
    <p class="total">Total: EUR {{ "{:,.2f}".format(inv.amount) }}</p>

    <p class="note">Demo invoice from a student project. The supplier, prices and parts are made up.</p>
  </div>
</body>
</html>
"""


@app.route("/invoice/<int:invoice_id>")
def invoice_page(invoice_id):
    inv = erp.get_invoice(invoice_id)
    if inv is None:
        return "Invoice not found", 404
    if inv["status"] != "posted":
        return "This invoice is still pending. Approve it in the dashboard first.", 400
    return render_template_string(INVOICE_PAGE, inv=inv)


if __name__ == "__main__":
    if not os.path.exists(erp.DB_FILE):
        print("No erp.db yet. Run the notebook first (it stores the data in the ERP).")
    app.run(port=5000)
