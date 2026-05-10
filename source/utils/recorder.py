import threading
import time
import io
from pathlib import Path
from PIL import Image
import imageio
from utils.logger import get_logger

logger = get_logger("recorder")

class VideoRecorder:
    """Records a Selenium session as a GIF by taking screenshots in a thread."""

    def __init__(self, driver, output_path: Path, interval: float = 0.5):
        self.driver = driver
        self.output_path = output_path
        self.interval = interval
        self.frames = []
        self._stop_event = threading.Event()
        self._thread = None
        self._start_time = None
        self._end_time = None

    def _capture_loop(self):
        logger.info("Recording started...")
        self._start_time = time.time()
        while not self._stop_event.is_set():
            try:
                # Get screenshot as bytes
                screenshot = self.driver.get_screenshot_as_png()
                img = Image.open(io.BytesIO(screenshot))
                self.frames.append(img)
            except Exception as e:
                logger.debug("Recorder capture failed: %s", e)
            
            time.sleep(self.interval)

    def start(self):
        """Starts the recording thread."""
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stops the recording and saves the GIF."""
        self._stop_event.set()
        self._end_time = time.time()
        if self._thread:
            self._thread.join(timeout=2)
        
        if not self.frames:
            logger.warning("No frames captured, skipping GIF generation.")
            return

        # Calculate actual duration per frame to match real-time
        total_time = self._end_time - self._start_time
        frame_duration = total_time / len(self.frames)
        
        logger.info(
            "Saving recording to %s (%d frames, total %.1fs, %.2fs/frame)...", 
            self.output_path, len(self.frames), total_time, frame_duration
        )
        
        try:
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            imageio.mimsave(
                str(self.output_path), 
                self.frames, 
                format='GIF', 
                duration=frame_duration,
                loop=0
            )
            logger.info("Recording saved successfully.")
        except Exception as e:
            logger.error("Failed to save GIF: %s", e)
