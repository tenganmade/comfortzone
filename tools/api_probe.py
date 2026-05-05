"""Read-only API probe for the Comfortzone RX95 Loggamera endpoint.

Usage (from project root):
    python tools/api_probe.py

Reads credentials from ../secrets.local.json (one level up if run from tools/,
otherwise ./secrets.local.json). Calls ONLY the RawData endpoint -- no writes.

Outputs:
    tools/sample_response.json  -- full raw API response
    stdout                      -- summary table of every reading

Detects the structure of the response so we know exactly what we have to work
with when designing the v2.0 controller.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib import request, error

API_ENDPOINT = "https://platform.loggamera.se/Api/v1/RawData"
TIMEOUT_SEC = 30


def find_secrets_file() -> Path:
    here = Path(__file__).resolve().parent
    candidates = [
        here.parent / "secrets.local.json",
        here / "secrets.local.json",
        Path.cwd() / "secrets.local.json",
    ]
    for c in candidates:
        if c.is_file():
            return c
    raise FileNotFoundError(
        "secrets.local.json not found. Looked in: "
        + ", ".join(str(c) for c in candidates)
    )


def load_secrets() -> tuple[str, int]:
    path = find_secrets_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    api_key = data.get("api_key")
    device_id = data.get("device_id")
    if not api_key or not device_id:
        raise ValueError(
            "secrets.local.json must contain 'api_key' (string) and 'device_id' (int)."
        )
    return str(api_key), int(device_id)


def fetch_raw_data(api_key: str, device_id: int) -> dict:
    payload = json.dumps({"ApiKey": api_key, "DeviceId": device_id}).encode("utf-8")
    req = request.Request(
        API_ENDPOINT,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.monotonic()
    try:
        with request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            body = resp.read().decode("utf-8")
            elapsed = time.monotonic() - t0
            print(f"[probe] HTTP {resp.status} in {elapsed:.2f}s "
                  f"(content-type: {resp.headers.get('Content-Type')})")
    except error.HTTPError as e:
        elapsed = time.monotonic() - t0
        print(f"[probe] HTTPError {e.code} after {elapsed:.2f}s: {e.reason}")
        raise

    try:
        return json.loads(body)
    except json.JSONDecodeError:
        print("[probe] Response was not JSON. First 500 chars:")
        print(body[:500])
        raise


def categorise_value(v: str | None) -> str:
    if v is None:
        return "None"
    s = v.strip()
    if s == "":
        return "empty-string"
    try:
        int(s)
        return "int-string"
    except ValueError:
        pass
    try:
        float(s)
        return "float-string"
    except ValueError:
        pass
    return "string"


def summarise(payload: dict) -> None:
    if "Error" in payload and payload["Error"]:
        print(f"[probe] API returned error: {payload['Error']}")
    data = payload.get("Data") or {}
    log_ts = data.get("LogDateTimeUtc")
    values = data.get("Values") or []
    print(f"[probe] LogDateTimeUtc = {log_ts}")
    print(f"[probe] Values count   = {len(values)}")
    print()

    name_w, val_w, type_w = 38, 12, 14
    print(f"{'ClearTextName'.ljust(name_w)} {'Value'.ljust(val_w)} "
          f"{'Type'.ljust(type_w)}  Unit / ValueType")
    print("-" * (name_w + val_w + type_w + 30))

    for item in values:
        if not isinstance(item, dict):
            continue
        name = str(item.get("ClearTextName", "?"))
        value = item.get("Value")
        v_str = "" if value is None else str(value)
        kind = categorise_value(v_str)
        unit = item.get("UnitPresentation") or item.get("UnitType") or ""
        vtype = item.get("ValueType") or ""
        meta = f"{vtype} {unit}".strip()
        print(f"{name[:name_w].ljust(name_w)} "
              f"{v_str[:val_w].ljust(val_w)} "
              f"{kind.ljust(type_w)}  {meta}")


def main() -> int:
    print(f"[probe] Started {datetime.now(timezone.utc).isoformat()}")
    try:
        api_key, device_id = load_secrets()
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as e:
        print(f"[probe] Secrets error: {e}", file=sys.stderr)
        return 2

    print(f"[probe] Using DeviceId {device_id} (api_key length {len(api_key)})")
    print(f"[probe] Calling {API_ENDPOINT} ...")

    try:
        payload = fetch_raw_data(api_key, device_id)
    except Exception as e:
        print(f"[probe] Request failed: {e}", file=sys.stderr)
        return 1

    out_path = Path(__file__).resolve().parent / "sample_response.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(f"[probe] Full response written to {out_path}")
    print()
    summarise(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
