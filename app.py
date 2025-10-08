from flask import Flask, request, render_template
import pandas as pd
import os
from ecropbot import run_ecrop_bot, load_license_map_from_sheet

app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        village_code = request.form["village_code"]
        license_key = request.form["license_key"]
        file = request.files["excel_file"]

        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(filepath)

        license_map = load_license_map_from_sheet()
        expected_key = license_map.get(village_code)
        if license_key != expected_key:
            return "❌ Invalid license key"

        df = pd.read_excel(filepath)
        log_output = []

        run_ecrop_bot(df, username, password, log_output, village_code)

        return "<br>".join(log_output)

    return render_template("ecropform.html")
if __name__ == "__main__":
    app.run(debug=True)
