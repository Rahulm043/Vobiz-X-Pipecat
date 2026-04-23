from pyngrok import ngrok
import os
from dotenv import load_dotenv

load_dotenv()

try:
    # Try to start ngrok tunnel on port 7860
    public_url = ngrok.connect(7860).public_url
    print(f"NGROK_URL:{public_url}")
    with open("ngrok_url.txt", "w") as f:
        f.write(public_url)
except Exception as e:
    print(f"ERROR:{e}")
    with open("ngrok_error.txt", "w") as f:
        f.write(str(e))
