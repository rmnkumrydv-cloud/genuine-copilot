"""Boilerplate fixture B: the SAME Flask skeleton as app_a.py — identical
imports, ``app = Flask(__name__)``, ``/health`` route, two POST routes with the
same signatures, and ``__main__`` guard — but the route bodies do completely
different work (string reversal + vowel counting instead of numeric math).

Independently written apps that share a framework's shape: HIGH structural
similarity, LOW logic similarity (regression §8.4-2). Not a clone.
"""

from flask import Flask, jsonify, request

app = Flask(__name__)

_VOWELS = {"a", "e", "i", "o", "u"}


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/reverse", methods=["POST"])
def reverse_text():
    data = request.get_json()
    text = data.get("text", "")
    flipped = text[::-1]
    shout = flipped.upper()
    return jsonify({"reversed": flipped, "shout": shout})


@app.route("/count", methods=["POST"])
def count_vowels():
    data = request.get_json()
    text = data.get("text", "")
    found = 0
    for char in text:
        if char in _VOWELS:
            found += 1
    return jsonify({"vowels": found})


if __name__ == "__main__":
    app.run(debug=True)
