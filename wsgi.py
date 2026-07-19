from app import create_app
from app.config import CONFIG

app = create_app()

if __name__ == "__main__":
    app.run(host=CONFIG["host"], port=CONFIG["port"], debug=True)
