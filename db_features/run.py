import logging
from app import create_app

logging.basicConfig(
    level=logging.INFO,   # <-- allow INFO and above
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

app = create_app()

if __name__ == "__main__":
    # bind to all interfaces so Windows browser can see the WSL server
    app.run(host="0.0.0.0", port=5000, debug=True)
