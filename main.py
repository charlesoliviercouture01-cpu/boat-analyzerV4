from flask import Flask, request, render_template_string
import pandas as pd
import os

app = Flask(__name__)

# ================= CONFIG =================
CFG = {
    "TPS_MIN": 97.0,
    "LAMBDA_MIN": 0.80,
    "LAMBDA_MAX": 0.92,
    "FUEL_MIN": 317,
    "FUEL_MAX": 372,
    "AMBIENT_OFFSET": 15,
    "CHEAT_DELAY_SEC": 0.5
}

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

<h1 class="text-center mb-4">{{ etat }}</h1>

<form method="post" action="/upload" enctype="multipart/form-data">

<div class="row mb-2">
  <div class="col"><input class="form-control" type="date" name="date_depart" required></div>
  <div class="col"><input class="form-control" type="time" name="heure_depart" required></div>
  <div class="col"><input class="form-control" name="numero" placeholder="Numéro embarcation" required></div>
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
<div class="table-responsive">{{ table|safe }}</div>
{% endif %}

</div>
</body>
</html>
"""

# ================= ANALYSE =================
def analyze(df, ambient_temp):

    # Colonnes requises EXACTES (selon ton fichier)
    REQUIRED = [
        "TPS (Main)",
        "Fuel Pressure",
        "IAT",
        "ECT",
        "Section Time"
    ]

    for c in REQUIRED:
        if c not in df.columns:
            raise ValueError(f"Colonne manquante : {c}")

    # Conversion SAFE
    for c in REQUIRED:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    lambda_cols = [c for c in df.columns if "lambda" in c.lower()]
    if not lambda_cols:
        raise ValueError("Aucune colonne Lambda détectée")

    df["Lambda"] = df[lambda_cols].apply(pd.to_numeric, errors="coerce").mean(axis=1)

    df = df.dropna()

    # ===== CONDITIONS =====
    df["TPS_ACTIVE"] = df["TPS (Main)"] >= CFG["TPS_MIN"]
    df["LAMBDA_OK"] = (df["Lambda"] >= CFG["LAMBDA_MIN"]) & (df["Lambda"] <= CFG["LAMBDA_MAX"])
    df["FUEL_OK"] = (df["Fuel Pressure"] >= CFG["FUEL_MIN"]) & (df["Fuel Pressure"] <= CFG["FUEL_MAX"])
    df["IAT_OK"] = df["IAT"] <= ambient_temp + CFG["AMBIENT_OFFSET"]
    df["ECT_OK"] = df["ECT"] <= ambient_temp + CFG["AMBIENT_OFFSET"]

    # ❗ LOGIQUE SIMPLIFIÉE – ZÉRO ~
    df["OUT"] = (
        df["TPS_ACTIVE"]
        & (
            (~df["LAMBDA_OK"])
            | (~df["FUEL_OK"])
            | (~df["IAT_OK"])
            | (~df["ECT_OK"])
        )
    )

    # Temps
    df["dt"] = df["Section Time"].diff().fillna(0)

    acc = 0.0
    debut = []

    for out, dt in zip(df["OUT"], df["dt"]):
        if bool(out):
            acc += float(dt)
            debut.append(acc >= CFG["CHEAT_DELAY_SEC"])
        else:
            acc = 0.0
            debut.append(False)

    df["Début_triche"] = debut
    df["QUALIFIÉ"] = [not x for x in df["Début_triche"]]

    return df

# ================= ROUTES =================
@app.route("/")
def index():
    return render_template_string(HTML, table=None, etat="Boat Analyzer – prêt")

@app.route("/upload", methods=["POST"])
def upload():
    try:
        ambient_temp = float(request.form["ambient_temp"])
        file = request.files["file"]

        df = pd.read_csv(file, skiprows=19)
        df = analyze(df, ambient_temp)

        etat = "PASS"
        if any(df["Début_triche"]):
            t = df.loc[df["Début_triche"], "Section Time"].iloc[0]
            etat = f"CHEAT – Début à {t:.2f} s"

        table = df.head(60).to_html(classes="table table-dark table-striped", index=False)

        return render_template_string(HTML, table=table, etat=etat)

    except Exception as e:
        return f"<h2>Erreur</h2><pre>{e}</pre>", 500
