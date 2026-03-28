import os
import json
import gspread
from flask import Flask, render_template, request, jsonify
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# --- Configuration ---
MAIN_FILE_NAME = "Mess_Tracker"
USERS = ["Alie", "Anuj", "Bhrigu", "Jitul", "Raja", "Risha"]
WEIGHTS = {"Alie": 1, "Risha": 1, "Anuj": 2, "Bhrigu": 2, "Jitul": 2, "Raja": 2}

def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if os.path.exists("credentials.json"):
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    else:
        creds_json = os.environ.get("GOOGLE_CREDS")
        if not creds_json:
            raise ValueError("No Google Credentials found!")
        creds_dict = json.loads(creds_json)
        creds = ServiceAccountCredentials.from_json_dict(creds_dict, scope)
    return gspread.authorize(creds)

try:
    client = get_gspread_client()
    spreadsheet = client.open(MAIN_FILE_NAME)
except Exception as e:
    print(f"Connection Error: {e}")

def get_worksheet_safe(month_name, suffix):
    try:
        return spreadsheet.worksheet(f"{month_name}_{suffix}")
    except:
        return None

@app.route('/')
def index():
    return render_template('index.html', users=USERS)

@app.route('/get_data', methods=['POST'])
def get_data():
    month = request.json.get('month')
    filter_date = request.json.get('filter_date')
    exp_ws = get_worksheet_safe(month, "Expenses")
    att_ws = get_worksheet_safe(month, "Attendance")
    
    if not exp_ws or not att_ws:
        return jsonify({"error": f"Sheets for {month} not found."}), 404

    try:
        expenses = exp_ws.get_all_records(expected_headers=["Timestamp", "Date", "Payer", "Item", "Amount"])
        attendance = att_ws.get_all_records(expected_headers=["Date"] + USERS)

        # 1. Calculation Logic (Always use full data for math)
        total_spent = sum(float(r.get('Amount', 0) or 0) for r in expenses)
        paid_by_user = {u: 0.0 for u in USERS}
        for r in expenses:
            p = r.get('Payer')
            if p in paid_by_user:
                paid_by_user[p] += float(r.get('Amount', 0) or 0)

        meals_by_user = {u: 0 for u in USERS}
        total_units = 0
        for r in attendance:
            for u in USERS:
                if str(r.get(u, "")).upper() in ["1", "TRUE", "YES"]:
                    w = WEIGHTS.get(u, 0)
                    meals_by_user[u] += w
                    total_units += w

        unit_cost = total_spent / total_units if total_units > 0 else 0
        
        # 2. Filter Expenses for Display if date is picked
        display_expenses = expenses
        if filter_date:
            display_expenses = [r for r in expenses if r.get('Date') == filter_date]

        settlement = []
        for u in USERS:
            share = meals_by_user[u] * unit_cost
            settlement.append({
                "name": u, "paid": round(paid_by_user[u], 2),
                "units": meals_by_user[u], "balance": round(paid_by_user[u] - share, 2)
            })

        return jsonify({
            "expenses": display_expenses[::-1],
            "attendance": attendance[::-1],
            "settlement": settlement,
            "total_spent": round(total_spent, 2),
            "unit_cost": round(unit_cost, 2)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/add_entry', methods=['POST'])
def add_entry():
    data = request.json
    ws = get_worksheet_safe(data['month'], data['type'])
    if not ws: return jsonify({"error": "Sheet not found"}), 404

    if data['type'] == 'Expenses':
        ws.append_row([datetime.now().strftime("%Y-%m-%d %H:%M"), data['date'], data['payer'], data['item'], float(data['amount'])])
    else:
        row = [data['date']]
        for u in USERS: row.append(1 if data['att'].get(u) else 0)
        ws.append_row(row)
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)