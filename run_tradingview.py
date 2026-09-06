import json
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


# ============================================================
# AI TRADER
# TradingView Webhook + Cloudflare Quick Tunnel Manager
# ============================================================

ROOT = Path(__file__).resolve().parent

DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

STATUS_FILE = DATA_DIR / "tradingview_tunnel.json"
PUBLIC_URL_FILE = DATA_DIR / "tradingview_public_url.txt"

WEBHOOK_SCRIPT = ROOT / "run_webhook.py"

WEBHOOK_HOST = "127.0.0.1"
WEBHOOK_PORT = 8000

LOCAL_URL = f"http://{WEBHOOK_HOST}:{WEBHOOK_PORT}"
LOCAL_HEALTH_URL = f"{LOCAL_URL}/health"

WEBHOOK_PATH = "/webhook/tradingview"


# ============================================================
# Runtime state
# ============================================================

webhook_process = None
cloudflare_process = None

stop_event = threading.Event()

public_url = ""
webhook_url = ""

state_lock = threading.Lock()


# ============================================================
# Cloudflare URL pattern
# ============================================================

CLOUDFLARE_URL_PATTERN = re.compile(
    r"https://[a-zA-Z0-9-]+\.trycloudflare\.com"
)


# ============================================================
# Helpers
# ============================================================

def now_iso():
    return datetime.now(timezone.utc).isoformat()


def log(message):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)


def save_status(
    status,
    message="",
    public_url_value="",
):
    payload = {
        "status": status,
        "local_url": LOCAL_URL,
        "health_url": LOCAL_HEALTH_URL,
        "public_url": public_url_value,
        "webhook_url": (
            public_url_value.rstrip("/") + WEBHOOK_PATH
            if public_url_value
            else ""
        ),
        "message": message,
        "updated_at": now_iso(),
    }

    try:
        STATUS_FILE.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as exc:
        log(f"WARNING: Could not write status file: {exc}")

    if public_url_value:
        try:
            PUBLIC_URL_FILE.write_text(
                public_url_value.rstrip("/") + "\n",
                encoding="utf-8",
            )
        except Exception as exc:
            log(f"WARNING: Could not write public URL file: {exc}")


def clear_runtime_url():
    global public_url
    global webhook_url

    with state_lock:
        public_url = ""
        webhook_url = ""


# ============================================================
# Local webhook health check
# ============================================================

def local_webhook_is_alive():
    try:
        request = urllib.request.Request(
            LOCAL_HEALTH_URL,
            method="GET",
            headers={
                "User-Agent": "AI-Trader-TradingView-Manager/1.0"
            },
        )

        with urllib.request.urlopen(
            request,
            timeout=3,
        ) as response:

            if response.status != 200:
                return False

            body = response.read().decode(
                "utf-8",
                errors="replace",
            ).lower()

            return '"ok"' in body and "true" in body

    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        ConnectionError,
        OSError,
    ):
        return False

    except Exception:
        return False


# ============================================================
# Find cloudflared executable
# ============================================================

def find_cloudflared():
    """
    Find cloudflared.

    Priority:
    1. cloudflared.exe next to project
    2. cloudflared.exe in project tools folder
    3. cloudflared.exe in PATH
    4. cloudflared command in PATH
    """

    candidates = [
        ROOT / "cloudflared.exe",
        ROOT / "cloudflared",
        ROOT / "tools" / "cloudflared.exe",
        ROOT / "tools" / "cloudflared",
    ]

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    # Windows PATH lookup
    try:
        result = subprocess.run(
            ["where", "cloudflared"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0:
            for line in result.stdout.splitlines():
                line = line.strip()

                if line:
                    path = Path(line)

                    if path.exists():
                        return str(path)

    except Exception:
        pass

    return None


# ============================================================
# Process output reader
# ============================================================

def read_process_output(process, name):
    global public_url
    global webhook_url

    try:
        for raw_line in iter(process.stdout.readline, ""):

            if stop_event.is_set():
                break

            if not raw_line:
                break

            line = raw_line.rstrip()

            if not line:
                continue

            print(f"[{name}] {line}", flush=True)

            # ------------------------------------------------
            # Detect Cloudflare public URL
            # ------------------------------------------------

            match = CLOUDFLARE_URL_PATTERN.search(line)

            if match:

                detected_url = match.group(0).rstrip("/")

                with state_lock:
                    changed = detected_url != public_url

                    public_url = detected_url
                    webhook_url = (
                        detected_url
                        + WEBHOOK_PATH
                    )

                if changed:

                    save_status(
                        status="ONLINE",
                        message="Cloudflare Quick Tunnel is running",
                        public_url_value=detected_url,
                    )

                    print("", flush=True)
                    log("========================================")
                    log("TRADINGVIEW PUBLIC URL UPDATED")
                    log("========================================")
                    log(
                        f"PUBLIC HTTPS : {detected_url}"
                    )
                    log(
                        f"WEBHOOK URL  : {webhook_url}"
                    )
                    log("========================================")
                    print("", flush=True)

    except Exception as exc:

        if not stop_event.is_set():

            log(
                f"{name} output reader error: {exc}"
            )


# ============================================================
# Start webhook server
# ============================================================

def start_webhook():
    global webhook_process

    if not WEBHOOK_SCRIPT.exists():

        message = (
            f"Missing webhook script: "
            f"{WEBHOOK_SCRIPT}"
        )

        log("ERROR: " + message)

        save_status(
            status="ERROR",
            message=message,
        )

        return False

    log("Starting TradingView Webhook Server...")
    log(f"Script: {WEBHOOK_SCRIPT}")
    log(f"Local URL: {LOCAL_URL}")

    try:

        webhook_process = subprocess.Popen(
            [
                sys.executable,
                str(WEBHOOK_SCRIPT),
            ],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=getattr(
                subprocess,
                "CREATE_NEW_PROCESS_GROUP",
                0,
            ),
        )

        thread = threading.Thread(
            target=read_process_output,
            args=(webhook_process, "WEBHOOK"),
            daemon=True,
        )

        thread.start()

        # Give Uvicorn time to start
        for _ in range(20):

            if stop_event.is_set():
                break

            if local_webhook_is_alive():

                log(
                    "TradingView Webhook Server is ONLINE"
                )

                save_status(
                    status="LOCAL",
                    message=(
                        "Local webhook is online; "
                        "waiting for Cloudflare URL"
                    ),
                )

                return True

            time.sleep(0.5)

        # Check if process crashed
        if webhook_process.poll() is not None:

            message = (
                "run_webhook.py stopped unexpectedly. "
                f"Exit code: {webhook_process.returncode}"
            )

            log("ERROR: " + message)

            save_status(
                status="ERROR",
                message=message,
            )

            return False

        # Process still running but health endpoint not ready
        log(
            "WARNING: Webhook process is running "
            "but /health is not responding yet."
        )

        save_status(
            status="STARTING",
            message=(
                "Webhook process started; "
                "waiting for /health"
            ),
        )

        return True

    except Exception as exc:

        message = (
            f"Could not start webhook server: {exc}"
        )

        log("ERROR: " + message)

        save_status(
            status="ERROR",
            message=message,
        )

        return False


# ============================================================
# Start Cloudflare Tunnel
# ============================================================

def start_cloudflare():
    global cloudflare_process

    cloudflared = find_cloudflared()

    if not cloudflared:

        message = (
            "cloudflared was not found. "
            "Install it or make sure cloudflared.exe "
            "is available in PATH."
        )

        log("ERROR: " + message)

        save_status(
            status="ERROR",
            message=message,
        )

        return False

    log("Cloudflared found:")
    log(cloudflared)

    log(
        "Starting Cloudflare Quick Tunnel..."
    )

    log(
        f"Tunnel target: {LOCAL_URL}"
    )

    try:

        cloudflare_process = subprocess.Popen(
            [
                cloudflared,
                "tunnel",
                "--url",
                LOCAL_URL,
            ],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=getattr(
                subprocess,
                "CREATE_NEW_PROCESS_GROUP",
                0,
            ),
        )

        thread = threading.Thread(
            target=read_process_output,
            args=(
                cloudflare_process,
                "CLOUDFLARE",
            ),
            daemon=True,
        )

        thread.start()

        save_status(
            status="STARTING",
            message=(
                "Cloudflare tunnel is starting"
            ),
        )

        return True

    except Exception as exc:

        message = (
            f"Could not start Cloudflare: {exc}"
        )

        log("ERROR: " + message)

        save_status(
            status="ERROR",
            message=message,
        )

        return False


# ============================================================
# Monitor services
# ============================================================

def monitor_services():

    global public_url
    global webhook_url

    while not stop_event.is_set():

        time.sleep(2)

        if stop_event.is_set():
            break

        # ----------------------------------------------------
        # Check webhook
        # ----------------------------------------------------

        webhook_alive = local_webhook_is_alive()

        if not webhook_alive:

            if webhook_process is not None:

                if webhook_process.poll() is not None:

                    log(
                        "WARNING: Webhook server stopped."
                    )

                    save_status(
                        status="OFFLINE",
                        message=(
                            "Webhook server stopped"
                        ),
                    )

                    # Do not restart automatically here.
                    # Prevents duplicate servers.
                    stop_event.set()
                    break

        # ----------------------------------------------------
        # Check Cloudflare
        # ----------------------------------------------------

        if cloudflare_process is not None:

            if cloudflare_process.poll() is not None:

                log(
                    "WARNING: Cloudflare tunnel stopped."
                )

                save_status(
                    status="OFFLINE",
                    message=(
                        "Cloudflare tunnel stopped"
                    ),
                    public_url_value="",
                )

                clear_runtime_url()

                stop_event.set()
                break

        # ----------------------------------------------------
        # Determine current status
        # ----------------------------------------------------

        with state_lock:
            current_public_url = public_url

        if webhook_alive and current_public_url:

            save_status(
                status="ONLINE",
                message=(
                    "Webhook + Cloudflare tunnel "
                    "are online"
                ),
                public_url_value=current_public_url,
            )

        elif webhook_alive:

            save_status(
                status="LOCAL",
                message=(
                    "Local webhook is online; "
                    "waiting for public URL"
                ),
            )

        else:

            save_status(
                status="STARTING",
                message=(
                    "Waiting for local webhook"
                ),
            )


# ============================================================
# Shutdown
# ============================================================

def stop_process(process, name):

    if process is None:
        return

    try:

        if process.poll() is None:

            log(
                f"Stopping {name}..."
            )

            try:
                process.terminate()
            except Exception:
                pass

            # Wait briefly
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:

                log(
                    f"{name} did not stop gracefully. "
                    "Killing process..."
                )

                try:
                    process.kill()
                except Exception:
                    pass

    except Exception as exc:

        log(
            f"Error stopping {name}: {exc}"
        )


def shutdown():

    global webhook_process
    global cloudflare_process

    if stop_event.is_set():
        pass

    stop_event.set()

    log("")
    log("Stopping TradingView services...")

    # Stop Cloudflare first
    stop_process(
        cloudflare_process,
        "Cloudflare",
    )

    # Then webhook
    stop_process(
        webhook_process,
        "Webhook",
    )

    save_status(
        status="OFFLINE",
        message="TradingView services stopped",
    )

    log(
        "TradingView services stopped."
    )


# ============================================================
# Main
# ============================================================

def main():

    log("========================================")
    log("AI TRADER")
    log("TradingView Service Manager")
    log("========================================")

    log(f"Project: {ROOT}")
    log(f"Local webhook: {LOCAL_URL}")
    log(f"Health check: {LOCAL_HEALTH_URL}")
    log("")

    # --------------------------------------------------------
    # Initial status
    # --------------------------------------------------------

    save_status(
        status="STARTING",
        message="Starting TradingView services",
    )

    # --------------------------------------------------------
    # Start local webhook
    # --------------------------------------------------------

    if not start_webhook():

        shutdown()
        return 1

    # --------------------------------------------------------
    # Start Cloudflare
    # --------------------------------------------------------

    if not start_cloudflare():

        shutdown()
        return 1

    # --------------------------------------------------------
    # Start monitoring
    # --------------------------------------------------------

    monitor_thread = threading.Thread(
        target=monitor_services,
        daemon=True,
    )

    monitor_thread.start()

    log("")
    log("========================================")
    log("TradingView services are running")
    log("========================================")
    log("")
    log(
        "Waiting for Cloudflare public URL..."
    )
    log("")
    log(
        "DO NOT CLOSE THIS WINDOW."
    )
    log(
        "Closing it will stop the webhook and tunnel."
    )
    log("")

    # --------------------------------------------------------
    # Main wait loop
    # --------------------------------------------------------

    try:

        while not stop_event.is_set():

            # If either process stops,
            # monitoring will set stop_event.
            time.sleep(1)

    except KeyboardInterrupt:

        log("")
        log(
            "CTRL+C detected."
        )

    finally:

        shutdown()

    return 0


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    raise SystemExit(main())