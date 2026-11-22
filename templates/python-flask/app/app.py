from flask import Flask

app = Flask(__name__)


@app.get("/")
def index():
    # Starting point: add the vulnerable feature here. The flag is in /flag.txt.
    return "Replace this page with your challenge.\n"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
