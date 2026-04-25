import json

def parse_and_format_whatsapp(custom_message):
    """
    Simulates the robust parsing logic used in bot_live.py.
    """
    # 1. Handle cases where the input is a dict (standard tool call args)
    if isinstance(custom_message, dict):
        custom_message = custom_message.get("custom_message") or custom_message.get("arguments", {}).get("custom_message", "")
    
    # 2. Final stringification/fallback
    custom_message = str(custom_message) if custom_message else "Amader institute somporke daitails pathiye dilam."

    # 3. Define the Template (Standard Information)
    template = """
SUKANYA CLASSES | Class 1–12 (CBSE/ICSE)
🌟 We teach the way students learn🌟 

✅ Experienced Faculty
✅ Practical & Computer Labs
✅ CCTV & Transport

📍 Centres: Fuljhore, Benachity, Raniganj
🎓 Admission Open | Session 2026–27
📞 8637583173 / 9002005510 / 9002005526
YT: https://youtube.com/shorts/j5FAoTYgacI?feature=shared
FB: https://www.facebook.com/sukanyaclasses
IG: https://www.instagram.com/sukanyaclasses
🌐 sukanyaclasses.com
"""

    # 4. Concatenate
    final_message = f"{custom_message}\n\n{template}".strip()
    
    return final_message

# --- TEST CASE ---
if __name__ == "__main__":
    # Simulated model output (as a dict, which Pipecat often passes)
    model_output = {"custom_message": "Phuljhore Branch: 1st Fl, Keshob Kunj Apt, Sarat Pally, Nehru Rd."}
    
    print("--- RAW MODEL INPUT ---")
    print(model_output)
    
    # Force UTF-8 for printing to avoid Windows charmap errors
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    
    print("\n--- EXTRACTED & FORMATTED MESSAGE ---")
    print(parse_and_format_whatsapp(model_output))
