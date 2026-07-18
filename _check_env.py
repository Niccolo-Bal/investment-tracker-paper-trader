import os
from pathlib import Path

# Pull User-level env into os.environ (Windows)
try:
    import winreg
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment")
    i = 0
    while True:
        try:
            name, value, _ = winreg.EnumValue(key, i)
            if name and value and name not in os.environ:
                os.environ[name] = str(value)
            i += 1
        except OSError:
            break
    winreg.CloseKey(key)
except Exception as e:
    print("winreg note:", e)

for k in ("GMAIL-INVESTMENT-UPDATE-EMAIL", "GMAIL-INVESTMENT-UPDATE-APP-PW", "PERSONAL-EMAIL", "OLLAMA_HOST", "OLLAMA_MODEL"):
    v = os.environ.get(k)
    if not v:
        print(f"{k}: MISSING")
    elif "PW" in k or "PASSWORD" in k.upper():
        print(f"{k}: set (len={len(v)})")
    else:
        print(f"{k}: set ({v[:3]}...)")
