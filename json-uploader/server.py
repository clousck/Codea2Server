from flask import Flask, request, abort
from werkzeug.utils import secure_filename
import os
from functools import wraps

app = Flask(__name__)

UPLOAD_DIR = "/data/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

API_KEY = os.environ.get("UPLOAD_API_KEY", "cambia-esto-por-algo-random")

# .csv se mantiene para no rechazar lo ya recogido con la versión anterior
ALLOWED_EXTENSIONS = (".json", ".csv")


def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get("X-API-Key")
        if key != API_KEY:
            abort(401, description="invalid or missing API key")
        return f(*args, **kwargs)
    return decorated


@app.route('/upload', methods=['POST'])
@require_api_key
def upload_telemetry():
    if 'file' not in request.files:
        return {"error": "no file field"}, 400

    file = request.files['file']

    # secure_filename neutraliza rutas tipo ../../ en el nombre que llega del cliente
    filename = secure_filename(file.filename or "")
    if not filename:
        return {"error": "empty filename"}, 400

    if not filename.lower().endswith(ALLOWED_EXTENSIONS):
        return {"error": "must be .json or .csv"}, 400

    # Sin prefijo de fecha: se guarda con el nombre que manda el visor,
    # {pin}_{sessionId}.json, que ya es único por el sessionId.
    saved_as = filename
    file.save(os.path.join(UPLOAD_DIR, saved_as))

    return {"status": "ok", "saved_as": saved_as}, 200


@app.route('/health', methods=['GET'])
def health():
    return {"status": "alive"}, 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)

