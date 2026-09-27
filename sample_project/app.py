import os
import logging
from flask import Flask, jsonify

app = Flask(__name__)
logger = logging.getLogger(__name__)

# Configured from env
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'default-key')
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'ready': True})

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({'error': 'Server error'}), 500

if __name__ == '__main__':
    app.run(debug=False)
