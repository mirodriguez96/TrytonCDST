import uvicorn
from tools import get_config
config = get_config()

try:
    CERT_FILE = config.get('SSL', 'cert_file')
    KEY_FILE = config.get('SSL', 'key_file')
except:
    CERT_FILE = None
    KEY_FILE = None

if __name__ == '__main__':
    uvicorn.run('main:app', port=8010, host='0.0.0.0',
        reload=True,
        ssl_keyfile=KEY_FILE,
        ssl_certfile=CERT_FILE)
