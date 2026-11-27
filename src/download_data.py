"""Download the public Delhivery trip dataset (Sep-Oct 2018) and verify it."""
import hashlib
import sys
import urllib.request
from config import DATA_URL, RAW, RAW_FILE, RAW_SHA256


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    if RAW_FILE.exists() and sha256(RAW_FILE) == RAW_SHA256:
        print(f"already present and verified: {RAW_FILE}")
        return
    print(f"downloading {DATA_URL}")
    urllib.request.urlretrieve(DATA_URL, RAW_FILE)
    got = sha256(RAW_FILE)
    if got != RAW_SHA256:
        sys.exit(f"checksum mismatch: expected {RAW_SHA256}, got {got}")
    print(f"saved and verified: {RAW_FILE}")


if __name__ == "__main__":
    main()
