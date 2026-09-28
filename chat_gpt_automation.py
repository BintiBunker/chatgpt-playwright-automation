
import logging
import os
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright


# ============================================================
# LOGGING SETUP
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)

log = logging.getLogger("chatgpt-bot")


# ============================================================
# CONFIGURATION
# ============================================================

# Prompt that will be sent to ChatGPT
PROMPT = "Write a short note on cats"

# ChatGPT prompt box
PROMPT_BOX = "#prompt-textarea"

# Chrome DevTools Protocol address
CDP_URL = "http://127.0.0.1:9222"

# Chrome executable and isolated automation profile
CHROME_EXE = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
CHROME_PROFILE = Path.home() / "chrome-automation"

# Name of the output video
VIDEO_OUTPUT = Path("automation.mp4")

# Frames captured per second
FPS = 2


# ============================================================
# MP4 RECORDER
# ============================================================

class Mp4Recorder:

    def __init__(self, page, output_path, fps=2):
        self.page = page
        self.output_path = Path(output_path)
        self.fps = fps

        # Temporary folder for screenshots
        self.frame_dir = Path(
            tempfile.mkdtemp(
                prefix="chatgpt-frames-"
            )
        )

        self.frame_number = 0

    # --------------------------------------------------------
    # Capture screenshot
    # --------------------------------------------------------

    def capture(self):
        frame_path = (
            self.frame_dir
            / f"frame_{self.frame_number:06d}.png"
        )

        try:
            self.page.screenshot(
                path=str(frame_path),
                full_page=False
            )

            self.frame_number += 1

        except Exception as e:
            log.warning(
                "Could not capture screenshot: %s",
                e
            )

    # --------------------------------------------------------
    # Create MP4 using FFmpeg
    # --------------------------------------------------------

    def finish(self):

        if self.frame_number == 0:

            log.error(
                "No screenshots were captured."
            )

            shutil.rmtree(
                self.frame_dir,
                ignore_errors=True
            )

            return

        # Find FFmpeg
        ffmpeg = shutil.which("ffmpeg")

        if ffmpeg is None:

            log.error(
                "FFmpeg was not found."
            )

            log.error(
                "Please install FFmpeg and add it "
                "to your PATH."
            )

            log.error(
                "Your screenshots are available here:"
            )

            log.error(
                "%s",
                self.frame_dir
            )

            return

        # ----------------------------------------------------
        # FFmpeg command
        # ----------------------------------------------------

        command = [
            ffmpeg,

            "-y",
            "-framerate",
            str(self.fps),

            "-i",
            str(
            self.frame_dir
            / "frame_%06d.png"
            ),

            "-c:v",
            "libx264",

            # Make width and height even
            "-vf",
            "scale=trunc(iw/2)*2:trunc(ih/2)*2",

            "-pix_fmt",
            "yuv420p",

            str(self.output_path),
        ]

        log.info(
            "Creating MP4 video..."
        )

        try:

            subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
            )

            log.info(
                "=========================================="
            )

            log.info(
                "✓ MP4 CREATED SUCCESSFULLY"
            )

            log.info(
                "Video: %s",
                self.output_path.resolve()
            )

            log.info(
                "=========================================="
            )

        except subprocess.CalledProcessError as e:

            log.error(
                "FFmpeg failed."
            )

            log.error(
                "%s",
                e.stderr
            )

        except OSError as e:

            log.error(
                "Could not run FFmpeg: %s",
                e
            )

        finally:

            # Delete temporary screenshots
            shutil.rmtree(
                self.frame_dir,
                ignore_errors=True
            )


# ============================================================
# START PLAYWRIGHT
# ============================================================

def start_chrome_if_needed():
    version_url = f"{CDP_URL}/json/version"

    try:
        with urllib.request.urlopen(version_url, timeout=1):
            log.info("Chrome debugging endpoint is already available.")
            return
    except (urllib.error.URLError, TimeoutError, OSError):
        pass

    if not CHROME_EXE.is_file():
        raise FileNotFoundError(
            f"Chrome was not found at {CHROME_EXE}. Update CHROME_EXE in this script."
        )

    log.info("Starting Chrome with profile %s ...", CHROME_PROFILE)
    creation_flags = 0
    if os.name == "nt":
        creation_flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

    subprocess.Popen(
        [
            str(CHROME_EXE),
            "--remote-debugging-port=9222",
            f"--user-data-dir={CHROME_PROFILE}",
        ],
        creationflags=creation_flags,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(version_url, timeout=1):
                log.info("Chrome debugging endpoint is ready.")
                return
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.25)

    raise TimeoutError("Chrome did not expose its debugging endpoint on port 9222.")


start_chrome_if_needed()

with sync_playwright() as p:

    # --------------------------------------------------------
    # CONNECT TO CHROME
    # --------------------------------------------------------

    log.info(
        "Connecting to Chrome at %s ...",
        CDP_URL
    )

    try:

        browser = p.chromium.connect_over_cdp(
            CDP_URL
        )

    except Exception as e:

        log.error(
            "Could not connect to Chrome."
        )

        log.error(
            "Error: %s",
            e
        )

        log.error(
            ""
        )

        log.error(
            "Make sure Chrome was started with:"
        )

        log.error(
            "--remote-debugging-port=9222"
        )

        raise


    log.info(
        "✓ Connected to Chrome."
    )


    # --------------------------------------------------------
    # GET EXISTING BROWSER CONTEXT
    # --------------------------------------------------------

    if not browser.contexts:

        log.error(
            "No browser context found."
        )

        browser.close()

        raise RuntimeError(
            "No Chrome browser context available."
        )


    context = browser.contexts[0]

    log.info(
        "Using existing browser context."
    )

    log.info(
        "Number of contexts: %d",
        len(browser.contexts)
    )


    # --------------------------------------------------------
    # FIND EXISTING CHATGPT TAB
    # --------------------------------------------------------

    chatgpt = None

    for page in context.pages:

        if "chatgpt.com" in page.url:

            chatgpt = page

            log.info(
                "✓ Found existing ChatGPT tab."
            )

            log.info(
                "Reusing existing tab."
            )

            break


    # --------------------------------------------------------
    # OPEN CHATGPT IF NOT ALREADY OPEN
    # --------------------------------------------------------

    if chatgpt is None:

        log.info(
            "No ChatGPT tab found."
        )

        log.info(
            "Opening a new ChatGPT tab..."
        )

        chatgpt = context.new_page()

        chatgpt.goto(
            "https://chatgpt.com",
            wait_until="domcontentloaded"
        )


    # Bring ChatGPT to the front
    chatgpt.bring_to_front()


    log.info(
        "ChatGPT page title: %r",
        chatgpt.title()
    )


    # ========================================================
    # WAIT FOR CHATGPT PROMPT BOX
    # ========================================================

    log.info(
        "Waiting for ChatGPT prompt box..."
    )

    try:

        chatgpt.wait_for_selector(
            PROMPT_BOX,
            state="visible",
            timeout=120000
        )

        log.info(
            "✓ Prompt box is visible."
        )

        log.info(
            "ChatGPT is ready."
        )

    except Exception as e:

        log.error(
            "Prompt box did not appear."
        )

        log.error(
            "Error: %s",
            e
        )

        # Save screenshot for debugging
        try:

            chatgpt.screenshot(
                path="chatgpt_error.png"
            )

            log.error(
                "Screenshot saved as:"
            )

            log.error(
                "chatgpt_error.png"
            )

        except Exception:
            pass

        browser.close()

        raise


    # ========================================================
    # CREATE VIDEO RECORDER
    # ========================================================

    recorder = Mp4Recorder(
        page=chatgpt,
        output_path=VIDEO_OUTPUT,
        fps=FPS
    )


    # Capture initial ChatGPT page
    recorder.capture()


    # ========================================================
    # MANUAL LOGIN CHECK
    # ========================================================

    log.info(
        ""
    )

    log.info(
        "If you are not logged into ChatGPT,"
    )

    log.info(
        "log in manually in the Chrome window."
    )

    log.info(
        "Complete any verification if required."
    )

    log.info(
        ""
    )

    input(
        "Press ENTER when ChatGPT is ready..."
    )


    # Capture screen after login
    recorder.capture()


    # ========================================================
    # SEND PROMPT
    # ========================================================

    try:

        # ----------------------------------------------------
        # Click prompt box
        # ----------------------------------------------------

        log.info(
            "Clicking ChatGPT prompt box..."
        )

        chatgpt.locator(
            PROMPT_BOX
        ).click()


        # ----------------------------------------------------
        # Type prompt
        # ----------------------------------------------------

        log.info(
            "Typing prompt:"
        )

        log.info(
            "%s",
            PROMPT
        )

        chatgpt.keyboard.type(
            PROMPT
        )


        # Capture the screen with the prompt typed
        recorder.capture()


        # ----------------------------------------------------
        # FIND SEND BUTTON
        # ----------------------------------------------------

        log.info(
            "Looking for Send button..."
        )

        send_button = chatgpt.locator(
            "button[data-testid='send-button']"
        )


        # ----------------------------------------------------
        # CLICK SEND
        # ----------------------------------------------------

        try:

            send_button.click(
                timeout=5000
            )

            log.info(
                "✓ Send button clicked."
            )

        except Exception:

            log.info(
                "Send button was not found."
            )

            log.info(
                "Using Enter key instead..."
            )

            chatgpt.keyboard.press(
                "Enter"
            )

            log.info(
                "✓ Enter key pressed."
            )


        # Capture immediately after sending
        recorder.capture()


        # ====================================================
        # WAIT FOR ASSISTANT RESPONSE
        # ====================================================

        log.info(
            "Waiting for ChatGPT response..."
        )


        assistant_msg = chatgpt.locator(
            "[data-message-author-role='assistant']"
        ).last


        assistant_msg.wait_for(
            state="visible",
            timeout=60000
        )


        log.info(
            "✓ Assistant response appeared."
        )


        # ====================================================
        # MONITOR RESPONSE + RECORD VIDEO
        # ====================================================

        previous_text = ""

        stable_count = 0

        # Response is considered complete when
        # it remains unchanged for 3 checks.
        required_stable_checks = 3


        while stable_count < required_stable_checks:

            # Wait half a second
            chatgpt.wait_for_timeout(
                500
            )


            # Capture browser screenshot
            recorder.capture()


            # Read current response
            current_text = assistant_msg.inner_text()


            # ------------------------------------------------
            # Check if response changed
            # ------------------------------------------------

            if (
                current_text
                and current_text == previous_text
            ):

                stable_count += 1

            else:

                stable_count = 0


            previous_text = current_text


        # ====================================================
        # RESPONSE FINISHED
        # ====================================================

        log.info(
            ""
        )

        log.info(
            "✓ ChatGPT finished responding."
        )

        log.info(
            ""
        )

        log.info(
            "CHATGPT RESPONSE:"
        )

        log.info(
            "------------------------------------------"
        )

        log.info(
            "%s",
            previous_text
        )

        log.info(
            "------------------------------------------"
        )


        # ====================================================
        # KEEP FINAL RESPONSE ON SCREEN
        # ====================================================

        log.info(
            "Recording final response..."
        )


        # Keep the final response visible
        # for approximately 3 seconds.

        for _ in range(6):

            chatgpt.wait_for_timeout(
                500
            )

            recorder.capture()


        # ====================================================
        # CREATE MP4
        # ====================================================

        recorder.finish()


    # ========================================================
    # ERROR HANDLING
    # ========================================================

    except Exception as e:

        log.error(
            ""
        )

        log.error(
            "✗ Automation failed."
        )

        log.error(
            "Error: %s",
            e
        )


        # Save screenshot for debugging
        try:

            chatgpt.screenshot(
                path="chatgpt_error.png"
            )

            log.error(
                "Debug screenshot saved as:"
            )

            log.error(
                "chatgpt_error.png"
            )

        except Exception:
            pass


        # Try to create MP4 from frames captured
        # before the error.
        try:

            recorder.finish()

        except Exception:
            pass


    # ========================================================
    # KEEP CHROME OPEN
    # ========================================================

    log.info(
        ""
    )

    log.info(
        "Automation completed."
    )

    log.info(
        "Chrome will remain open."
    )

    input(
        "\nPress ENTER to disconnect from Chrome..."
    )


    # ========================================================
    # DISCONNECT
    # ========================================================

    log.info(
        "Disconnecting from Chrome..."
    )

    browser.close()

    log.info(
        "✓ Disconnected from Chrome."
    )

    log.info(
        "Your Chrome window remains open."
    )

    log.info(
        "Goodbye!"
    )


