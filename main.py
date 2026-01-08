from flask import Flask, request, render_template_string, send_file, url_for
import pandas as pd
import os
from datetime import datetime

app = Flask(__name__)

# ================= CONFIG =================
CFG = {
    "TPS_MIN": 97.0,
    "LAMBDA_RANGE": (0.80, 0.92),
    "FUEL_RANGE": (317, 372),
    "TEMP_OFFSET": 15,
    "CHEAT_DELAY": 0.5
}

UPLOAD_DIR = "/tmp"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ================= HTML =================
HTML = """
<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Boat Data Analyzer</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
</head>

<body class="p-4 bg-dark text-light">
<div class="container">

<h1 class="text-center mb-4">{{ etat }}</h1>

<form method="post" action="/upload" enctype="multipart/form-data">

<div class="row mb-3">
  <div class="col">
    <input class="form-control" type="date" name="date_depart" required>
  </div>
  <div class="col">
    <input class="form-control" type="time" name="heure_depart" required>
  </div>
  <div class="col">
    <input class="form-control" type="text" name="numero_embarcation"
           placeholder="Numéro embarcation" required>
  </div>
</div>

<div class="row mb-3">
  <div class="col">
    <input class="form-control" type="number" step="0.1"
           name="ambient_temp" placeholder="Température ambiante (°C)" required>
  </div>
</div>

<input class="form-control mb-3" type="file" name="file" required>
<button class="btn btn-primary">Analyser</button>

</form>

{% if table %}
<hr>
<a class="btn btn-success" href="{{ download }}">Télécharger CSV</a>
<div class="table-responsive mt-3">{{ table|safe }}</div>
{% endif %}

</div>
</body>
</html>
"""

# ================= ANALYSE =================
def analyze_dataframe(df, ambient_temp):

    REQUIRED = [
        "Section Time",
        "TPS (Main)",
        "Lambda 1",
        "Fuel Pressure",
        "IAT",
        "ECT"
    ]

    for col in REQUIRED:
        if col not in df.columns:
            raise ValueError(f"Colonne manquante : {col}")

    df = df.copy()

    df["TPS_ACTIVE"] = df["TPS (Main)"] >= CFG["TPS_MIN"]
    df["LAMBDA_OK"] = df["Lambda 1"].between(*CFG["LAMBDA_RANGE"])
    df["FUEL_OK"] = df["Fuel Pressure"].between(*CFG["FUEL_RANGE"])
    df["IAT_OK"] = df["IAT"] <= ambient_temp + CFG["TEMP_OFFSET"]
    df["ECT_OK"] = df["ECT"] <= ambient_temp + CFG["TEMP_OFFSET"]

    df["OUT"] = df["TPS_ACTIVE"] & ~(
        df["LAMBDA_OK"] &
        df["FUEL_OK"] &
        df["IAT_OK"] &
        df["ECT_OK"]
    )

    df["dt"] = df["Section Time"].diff().fillna(0)

    acc = 0.0
    cheat = []

    for out, dt in zip(df["OUT"], df["dt"]):
        if out:
            acc += dt
            cheat.append(acc >= CFG["CHEAT_DELAY"])
        else:
            acc = 0.0
            cheat.append(False)

    df["DEBUT_TRICHE"] = cheat
    df["QUALIFIE"] = ~df["DEBUT_TRICHE"]

    return df

# ================= ROUTES =================
@app.route("/")
def index():
    return render_template_string(
        HTML,
        table=None,
        download=None,
        etat="Boat Data Analyzer"
    )

@app.route("/upload", methods=["POST"])
def upload():
    try:
        file = request.files["file"]
        ambient_temp = float(request.form["ambient_temp"])
        date_depart = request.form["date_depart"]
        heure_depart = request.form["heure_depart"]
        numero = request.form["numero_embarcation"]

        df = pd.read_csv(file, skiprows=19)
        df = analyze_dataframe(df, ambient_temp)

        df.insert(0, "Date départ", date_depart)
        df.insert(1, "Heure départ", heure_depart)
        df.insert(2, "Numéro embarcation", numero)

        rows = df[df["DEBUT_TRICHE"]]
        etat = "PASS"
        if not rows.empty:
            etat = f"CHEAT – Début à {rows['Section Time'].iloc[0]:.2f} s"

        fname = f"result_{datetime.now().timestamp()}.csv"
        path = os.path.join(UPLOAD_DIR, fname)
        df.to_csv(path, index=False)

        table = df.head(100).to_html(
            classes="table table-dark table-striped",
            index=False
        )

        return render_template_string(
            HTML,
            table=table,
            download=url_for("download", fname=fname),
            etat=etat
        )

    except Exception as e:
        return f"<h2>Erreur</h2><pre>{e}</pre>", 500

@app.route("/download")
def download():
    fname = request.args.get("fname")
    return send_file(os.path.join(UPLOAD_DIR, fname), as_attachment=True)


