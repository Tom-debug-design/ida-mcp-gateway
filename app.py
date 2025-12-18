from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/")
def home():
    return jsonify({
        "status": "ok",
        "service": "ida-mcp-gateway",
        "message": "IDA is alive 👋"
    })

@app.route("/ping")
def ping():
    return jsonify({"pong": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
