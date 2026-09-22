from app import app


def client():
    app.config["TESTING"] = True
    return app.test_client()
