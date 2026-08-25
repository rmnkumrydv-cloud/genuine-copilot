"""Boilerplate fixture A: a minimal Flask app skeleton (numeric service).

Paired with app_b.py, which shares the *identical* framework skeleton — same
imports, same ``app = Flask(__name__)``, same ``/health`` route, two more
POST routes with the same signatures, same ``__main__`` guard — but whose route
bodies do genuinely different work (numeric aggregation + factorial here vs.
string processing there).

This is regression case §8.4-2: independently written apps that share a
framework's shape must produce HIGH structural similarity but LOW logic
similarity, and therefore resolve to CLEAN, not flagged.
"""

from flask import Flask, jsonify, request

app = Flask(__name__)

_LIMITS = {"min": 0, "max": 100}


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/stats", methods=["POST"])
def stats():
    data = request.get_json()
    values = data.get("values", [])
    total = 0
    for value in values:
        total += value
    mean = total / len(values) if values else 0
    return jsonify({"sum": total, "mean": mean})


@app.route("/factorial", methods=["POST"])
def factorial():
    data = request.get_json()
    number = data.get("n", 0)
    result = 1
    while number > 1:
        result *= number
        number -= 1
    return jsonify({"result": result})


if __name__ == "__main__":
    app.run(debug=True)
