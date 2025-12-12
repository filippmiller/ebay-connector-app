import json

try:
    with open('railway_vars.json', 'r', encoding='utf-16') as f:
        data = json.load(f)
        print("Keys found:", list(data.keys()))
        if "DATABASE_URL" in data:
            print("DATABASE_URL found in railway_vars.json")
            # Write to .env
            with open('.env', 'a', encoding='utf-8') as env_file:
                env_file.write(f"\nDATABASE_URL={data['DATABASE_URL']}\n")
            print("Appended DATABASE_URL to .env")
        else:
            print("DATABASE_URL NOT found in railway_vars.json")
except Exception as e:
    print(f"Error reading utf-16: {e}")
    # Try utf-8
    try:
        with open('railway_vars.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            print("Keys found:", list(data.keys()))
            if "DATABASE_URL" in data:
                print("DATABASE_URL found in railway_vars.json")
                with open('.env', 'a', encoding='utf-8') as env_file:
                    env_file.write(f"\nDATABASE_URL={data['DATABASE_URL']}\n")
                print("Appended DATABASE_URL to .env")
    except Exception as e2:
        print(f"Error reading utf-8: {e2}")
