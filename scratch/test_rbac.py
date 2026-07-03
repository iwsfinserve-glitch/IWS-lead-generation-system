import requests
import json
import time

url = 'http://127.0.0.1:8000/api/v1/auth'

# 1. Login as Admin
login_resp = requests.post(f"{url}/login", data={'username': 'admin@example.com', 'password': 'admin123'})
if login_resp.status_code != 200:
    print('Admin Login failed:', login_resp.text)
    exit(1)

admin_token = login_resp.json()['access_token']
headers = {'Authorization': f'Bearer {admin_token}'}

print("✅ Admin Login successful.")

# 2. Create a manager
manager_data = {
    'name': 'Test Manager',
    'email': f'manager_{int(time.time())}@example.com',
    'password': 'password123',
    'role': 'manager'
}
mgr_resp = requests.post(f"{url}/register", json=manager_data, headers=headers)
if mgr_resp.status_code != 201:
    print('Manager creation failed:', mgr_resp.text)
    exit(1)
manager = mgr_resp.json()
print("✅ Manager created successfully:", manager['id'])

# 3. Create a sales rep reporting to the manager
rep_data = {
    'name': 'Test Rep',
    'email': f'rep_{int(time.time())}@example.com',
    'password': 'password123',
    'role': 'sales_rep',
    'manager_id': manager['id']
}
rep_resp = requests.post(f"{url}/register", json=rep_data, headers=headers)
if rep_resp.status_code != 201:
    print('Sales Rep creation failed:', rep_resp.text)
    exit(1)
rep = rep_resp.json()
print("✅ Sales Rep created successfully:", rep['id'])

# Verify the manager ID is set
if rep.get('manager_id') == manager['id']:
    print("✅ Sales Rep manager_id assigned correctly.")
else:
    print("❌ Sales Rep manager_id mismatch:", rep)

# 4. List users
users_resp = requests.get(f"{url}/users", headers=headers)
if users_resp.status_code == 200:
    print(f"✅ User list retrieved successfully. Total users: {len(users_resp.json())}")
else:
    print('❌ Failed to list users:', users_resp.text)

# 5. Delete the users
del_rep = requests.delete(f"{url}/users/{rep['id']}", headers=headers)
if del_rep.status_code == 204:
    print("✅ Sales Rep deleted successfully.")
else:
    print("❌ Sales Rep deletion failed:", del_rep.text)

del_mgr = requests.delete(f"{url}/users/{manager['id']}", headers=headers)
if del_mgr.status_code == 204:
    print("✅ Manager deleted successfully.")
else:
    print("❌ Manager deletion failed:", del_mgr.text)
