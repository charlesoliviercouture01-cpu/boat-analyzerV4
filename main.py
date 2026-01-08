from flask import Flask, request, render_template_string
import pandas as pd
import os
from datetime import datetime

app = Flask(__name__)

# ================= CONFIG =================
CFG = {
    "TPS_MIN": 97.0,
    "LAMBDA_RANGE": (0.80, 0.92),
    "FUEL_RANGE": (317, 372),
    "AMBIENT_OFFSET": 15,
    "CHEAT_DELAY_SEC": 0.5
}

UPLOAD_DIR = "/tmp"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ================= HTML =================
HTML = """
<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Boat Analyzer</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="p-4 bg-dark text-light">

<div class="container">
<h1 class="mb-4 text-center">{{ etat_global }}</h1>

<form method="post" action="/upload" enctype="multipart/form-data">

<div class="row mb-2">
  <div class="col"><input class="form-control" type="date" name="date_depart" required></div>
  <div class="col"><input class="form-control" type="time" name="heure_depart" required></div>
  <div class="col"><input class="form-control" name="numero_embarcation" placeholder="Numéro embarcation" required></div>
</div>

<div class="row mb-2">
  <div class="col-md-4">
    <input class="form-control" type="number" step="0.1"
           name="ambient_temp" placeholder="Température ambiante (°C)" required>
  </div>
</div>

<input class="form-control mb-2" type="file" name="file" required>
<button class="btn btn-primary">Analyser</button>
</form>

{% if table %}
<hr>
<div class="table-responsive mt-3">{{ table|safe }}</div>
{% endif %}
</div>

</body>
</html>
"""

# ================= ANALYSE =================
def analyze_dataframe(df, ambient_temp):

    REQUIRED = [
        "TPS (Main)",
        "Fuel Pressure",
        "IAT",
        "ECT",
        "Section Time"
    ]

    for col in REQUIRED:
        if col not in df.columns:
            raise ValueError(f"Colonne manquante : {col}")

    # Conversion stricte
    df["TPS (Main)"] = pd.to_numeric(df["TPS (Main)"], errors="coerce")
    df["Fuel Pressure"] = pd.to_numeric(df["Fuel Pressure"], errors="coerce")
    df["IAT"] = pd.to_numeric(df["IAT"], errors="coerce")
    df["ECT"] = pd.to_numeric(df["ECT"], errors="coerce")
    df["Section Time"] = pd.to_numeric(df["Section Time"], errors="coerce")

    df = df.dropna(subset=REQUIRED)

    # Lambda
    lambda_cols = [c for c in df.columns if "lambda" in c.lower()]
    if not lambda_cols:
        raise ValueError("Aucune colonne Lambda détectée")

    df["Lambda"] = df[lambda_cols].apply(pd.to_numeric, errors="coerce").mean(axis=1)

    # ===== FLAGS BOOLÉENS (CRITIQUE) =====
    df["TPS_ACTIVE"] = (df["TPS (Main)"] >= CFG["TPS_MIN"])
    df["Lambda_OK"] = df["Lambda"].between(*CFG["LAMBDA_RANGE"])
    df["Fuel_OK"] = df["Fuel Pressure"].between(*CFG["FUEL_RANGE"])
    df["IAT_OK"] = df["IAT"] <= ambient_temp + CFG["AMBIENT_OFFSET"]
    df["ECT_OK"] = df["ECT"] <= ambient_temp + CFG["AMBIENT_OFFSET"]

    # ⚠️ FORÇAGE EN BOOL
    for c in ["TPS_ACTIVE", "Lambda_OK", "Fuel_OK", "IAT_OK", "ECT_OK"]:
        df[c] = df[c].astype(bool)

    ok_all = (
        df["Lambda_OK"] &
        df["Fuel_OK"] &
        df["IAT_OK"] &
        df["ECT_OK"]
    )

    # ✅ PLUS AUCUN ~ SUR FLOAT
    df["OUT_RAW"] = df["TPS_ACTIVE"] & (~ok_all)

    # Temps
    df["dt"] = df["Section Time"].diff().fillna(0)

    acc = 0.0
    debut = []

    for out, dt in zip(df["OUT_RAW"], df["dt"]):
        if out:
            acc += float(dt)
            debut.append(acc >= CFG["CHEAT_DELAY_SEC"])
        else:
            acc = 0.0
            debut.append(False)

    df["Début_triche"] = pd.Series(debut, dtype=bool)
    df["QUALIFIÉ"] = ~df["Début_triche"].rolling(2).max().fillna(False)

    return df

# ================= ROUTES =================
@app.route("/")
def index():
    return render_template_string(HTML, table=None, etat_global="Boat Analyzer – prêt")

@app.route("/upload", methods=["POST"])
def upload():
    try:
        file = request.files["file"]
        ambient_temp = float(request.form["ambient_temp"])

        df = pd.read_csv(file, skiprows=19)
        df = analyze_dataframe(df, ambient_temp)

        etat = "PASS"
        if df["Début_triche"].any():
            t = df.loc[df["Début_triche"], "Section Time"].iloc[0]
            etat = f"CHEAT – Début à {t:.2f} s"

        table = df.head(80).to_html(
            classes="table table-dark table-striped",
            index=False
        )

        return render_template_string(
            HTML,
            table=table,
            etat_global=etat
        )

    except Exception as e:
        return f"<h2>Erreur</h2><pre>{e}</pre>", 500








