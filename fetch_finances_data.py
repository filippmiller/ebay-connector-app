import requests, json, sys

login_url = 'https://ebay-connector-frontend.pages.dev/api/auth/login'
creds = {'email': 'filippmiller@gmail.com', 'password': 'Airbus380+'}
resp = requests.post(login_url, json=creds)
if resp.status_code != 200:
    print('Login failed', resp.status_code, resp.text)
    sys.exit(1)

token = resp.json().get('access_token')
print('TOKEN', token)

# fetch first 5 rows of finances grid
data_url = 'https://ebay-connector-frontend.pages.dev/api/grids/finances/data?limit=5&offset=0'
headers = {'Authorization': f'Bearer {token}'}
resp2 = requests.get(data_url, headers=headers)
if resp2.status_code != 200:
    print('Data fetch failed', resp2.status_code, resp2.text)
    sys.exit(1)

data = resp2.json()
print(json.dumps(data, indent=2))
