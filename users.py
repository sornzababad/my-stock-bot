import json, os

_FILE = os.path.join(os.path.dirname(__file__), 'users.json')

def load_users() -> list:
    seed = os.getenv('USER_ID') or os.getenv('LINE_USER_ID')
    try:
        with open(_FILE) as f:
            users = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        users = []
    if seed and seed not in users:
        users.append(seed)
        _save(users)
    return users

def add_user(uid: str):
    users = load_users()
    if uid not in users:
        users.append(uid)
        _save(users)

def remove_user(uid: str):
    users = load_users()
    if uid in users:
        users.remove(uid)
        _save(users)

def _save(users: list):
    with open(_FILE, 'w') as f:
        json.dump(users, f)
