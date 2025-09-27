import os, time
from .stats import text_stats

class AIService:
    def __init__(self, ai_logger):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.logger = ai_logger

    def _log(self, direction: str, file_path: str, text: str, start: float, end: float):
        s = text_stats(text)
        rec = {
            "file": file_path,
            "direction": direction,
            "elapsed_ms": int((end-start)*1000),
            "bytes": len(text.encode("utf-8")),
            "chars": len(text),
            "words": s["words"],
            "sentences": s["sentences"],
            "loc": s["loc"] if direction == "response" else 0,
            "est_tokens": s["est_tokens"],
        }
        self.logger.append(rec)

    def generate_description(self, file_path: str, seeds: str) -> str:
        start = time.time()
        prompt = f"Generate a concise, accurate circuit description based on seeds:\n{seeds}"
        self._log("prompt", file_path, prompt, start, start)
        time.sleep(0.2)
        response = "This is a placeholder AI-generated description. Replace with model call."
        end = time.time()
        self._log("response", file_path, response, start, end)
        return response

    def generate_fmea(self, file_path: str) -> list:
        start = time.time()
        prompt = "Generate an initial FMEA table for this board."
        self._log("prompt", file_path, prompt, start, start)
        time.sleep(0.2)
        rows = [[
            "U1", "No output", "Board inoperable", "9",
            "Solder bridge", "3", "ICT + Visual", "5",
            "135", "Rework solder", "N. Manteufel", "2025-10-01",
            "", "9", "3", "4", "108"
        ]]
        end = time.time()
        self._log("response", file_path, "FMEA rows: 1", start, end)
        return rows

    def generate_testing(self, file_path: str) -> list:
        start = time.time()
        prompt = "Generate a starter testing table for this board."
        self._log("prompt", file_path, prompt, start, start)
        time.sleep(0.2)
        rows = [[
            "T-001", "Power-on current", "Measure input current @ 12V", "5", "10", "15", "mA"
        ]]
        end = time.time()
        self._log("response", file_path, "Testing rows: 1", start, end)
        return rows
