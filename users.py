import json, os

_FILE = os.path.join(os.path.dirname(__file__), 'users.json')

def load_users() -> list:
    try:
        with open(_FILE) as f:
            users = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        users = []

    # seed จาก env: USER_IDS="uid1,uid2,uid3" หรือ USER_ID="uid1"
    env_ids = os.getenv('USER_IDS', '')
    seeds = [u.strip() for u in env_ids.split(',') if u.strip()]
    if not seeds:
        single = os.getenv('USER_ID') or os.getenv('LINE_USER_ID')
        if single:
            seeds = [single]

    changed = False
    for uid in seeds:
        if uid not in users:
            users.append(uid)
            changed = True
    if changed:
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
