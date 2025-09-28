import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import math, traceback

# Try new SDK first (openai>=1.x). Fall back to legacy.
try:
    from openai import OpenAI  # type: ignore
    _OPENAI_V1 = True
except Exception:
    OpenAI = None  # type: ignore
    _OPENAI_V1 = False

try:
    import openai  # legacy API (openai<1.0)  # type: ignore
except Exception:  # pragma: no cover
    openai = None  # fallback


@dataclass
class AIResult:
    ok: bool
    text: str
    error: Optional[str]
    prompt_bytes: int
    response_bytes: int
    prompt_chars: int
    response_chars: int
    prompt_words: int
    response_words: int
    prompt_sentences: int
    response_sentences: int
    response_loc: int
    prompt_tokens_est: int
    response_tokens_est: int
    started_at: float
    ended_at: float

class AIService:
    """
    Minimal AI wrapper with:
      - Fail-safe stub if OpenAI isn't configured
      - Logging to .minipcb_ai/ai_usage.jsonl
      - Token/word/etc. estimates
    """

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)
        self.log_dir = self.project_root / ".minipcb_ai"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "ai_usage.jsonl"

        # Defaults + client setup
        self.default_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.timeout = float(os.getenv("OPENAI_TIMEOUT", "45"))
        self.max_retries = int(os.getenv("OPENAI_RETRIES", "3"))

        self._client = None
        api_key = os.environ.get("OPENAI_API_KEY")
        if _OPENAI_V1 and api_key:
            try:
                self._client = OpenAI(api_key=api_key)
            except Exception:
                self._client = None

    # ------------- Public API -------------
    def generate_description(self, html: str, seeds: Dict[str, Any]) -> AIResult:
        """
        Uses seeds['description_seed'] + a lightweight HTML scrape to produce prose.
        If OpenAI is unavailable, returns a deterministic stub so UI still flows.
        """
        started = time.time()
        prompt = self._build_description_prompt(html, seeds)

        # --- Call model (or stub) ---
        ok = True
        err = None
        try:
            if (self._client or openai) and os.getenv("OPENAI_API_KEY"):
                response_text = self._call_openai_chat(prompt)
                if not response_text:
                    ok = False
                    err = "Empty response from AI."
                    response_text = self._fallback_stub(prompt)
            else:
                response_text = self._fallback_stub(prompt)
        except Exception as e:
            ok = False
            err = f"OpenAI error: {e}"
            response_text = self._fallback_stub(prompt)

        ended = time.time()
        stats = self._stats(prompt, response_text, started, ended)

        # Log both prompt and response, tag task for ETA
        self._log_event(direction="prompt", file="-", meta=stats, payload=prompt, task="description")
        self._log_event(direction="response", file="-", meta=stats, payload=response_text, task="description")

        return AIResult(
            ok=ok,
            text=response_text,
            error=err,
            prompt_bytes=stats["prompt_bytes"],
            response_bytes=stats["response_bytes"],
            prompt_chars=stats["prompt_chars"],
            response_chars=stats["response_chars"],
            prompt_words=stats["prompt_words"],
            response_words=stats["response_words"],
            prompt_sentences=stats["prompt_sentences"],
            response_sentences=stats["response_sentences"],
            response_loc=stats["response_loc"],
            prompt_tokens_est=stats["prompt_tokens_est"],
            response_tokens_est=stats["response_tokens_est"],
            started_at=started,
            ended_at=ended,
        )


    # ------------- Internals -------------
    def _call_openai_chat(self, prompt: str) -> str:
        """
        Calls OpenAI chat (supports both new and legacy SDKs) with retries.
        Raises on hard failure so caller can switch to stub and log an error.
        """
        messages = [
            {"role": "system", "content": "You are an assistant that writes clear, technical product descriptions."},
            {"role": "user", "content": prompt},
        ]
        model = (os.getenv("OPENAI_MODEL") or self.default_model or "gpt-4o-mini").strip()

        last_err = None
        start = time.time()
        for attempt in range(self.max_retries):
            try:
                if self._client is not None:
                    # New SDK (>=1.x)
                    resp = self._client.chat.completions.create(
                        model=model,
                        messages=messages,
                        temperature=0.4,
                        max_tokens=700,
                        timeout=self.timeout,
                    )
                    return (resp.choices[0].message.content or "").strip()

                # Legacy SDK path (<1.0)
                if not openai or not getattr(openai, "ChatCompletion", None):
                    raise RuntimeError(
                        "OpenAI SDK not available or incompatible. "
                        "Install/upgrade with: pip install --upgrade openai"
                    )
                openai.api_key = os.environ.get("OPENAI_API_KEY")
                resp = openai.ChatCompletion.create(  # type: ignore
                    model=model,
                    messages=messages,
                    temperature=0.4,
                    max_tokens=700,
                    timeout=self.timeout,
                )
                try:
                    return resp["choices"][0]["message"]["content"].strip()
                except Exception:
                    return ""

            except Exception as e:
                last_err = e
                msg = str(e)
                retryable = any(
                    s in msg for s in ("429", "timeout", "Timeout", "502", "503", "504",
                                       "Rate limit", "ServiceUnavailableError", "APIConnectionError")
                )
                if attempt < self.max_retries - 1 and retryable:
                    time.sleep(1.5 ** attempt)
                    continue
                # give up
                raise RuntimeError(f"OpenAI call failed after {attempt+1} attempt(s): {msg}") from e


    def _fallback_stub(self, prompt: str) -> str:
        # A deterministic text so UI & logging function reliably during setup
        return (
            "Summary\n\n"
            "This board implements the described functionality. Replace this with real AI output by setting "
            "OPENAI_API_KEY and (optionally) OPENAI_MODEL.\n"
        )

    def _scrape_title(self, html: str) -> Tuple[str, str]:
        # Return (PN, Title) best effort
        m = re.search(r"(?is)<title>\s*([^<|]+)\s*\|\s*([^<]+)</title>", html)
        if m:
            return m.group(1).strip(), m.group(2).strip()
        h1 = re.search(r"(?is)<h1[^>]*>(.*?)</h1>", html)
        if h1:
            txt = re.sub(r"<[^>]+>", "", h1.group(1)).strip()
            dash = re.split(r"[–-]", txt, maxsplit=1)
            if len(dash) == 2:
                return dash[0].strip(), dash[1].strip()
            return "", txt
        return "", ""

    def _build_description_prompt(self, html: str, seeds: Dict[str, Any]) -> str:
        pn, title = self._scrape_title(html)
        seed = (seeds or {}).get("description_seed", "")
        desc = (
            f"Board: {pn} — {title}\n\n"
            "Write a clear, concise description for the product page. Avoid bullet points. "
            "Use simple paragraphs. Include the core purpose, main functional blocks, and practical testing notes.\n\n"
        )
        if seed:
            desc += f"Guidance:\n{seed}\n\n"
        return desc

    def _stats(self, prompt: str, response: str, started: float, ended: float) -> Dict[str, Any]:
        def words(s: str) -> int:
            return len(re.findall(r"\b\w+\b", s))
        def sentences(s: str) -> int:
            return len(re.findall(r"[.!?]+(?:\s|$)", s)) or (1 if s.strip() else 0)
        def loc(s: str) -> int:
            return len([ln for ln in s.splitlines() if ln.strip()])

        prompt_chars = len(prompt)
        resp_chars = len(response)
        return {
            "prompt_bytes": len(prompt.encode("utf-8")),
            "response_bytes": len(response.encode("utf-8")),
            "prompt_chars": prompt_chars,
            "response_chars": resp_chars,
            "prompt_words": words(prompt),
            "response_words": words(response),
            "prompt_sentences": sentences(prompt),
            "response_sentences": sentences(response),
            "response_loc": loc(response),
            "prompt_tokens_est": max(1, prompt_chars // 4),
            "response_tokens_est": max(1, resp_chars // 4),
            "duration_sec": max(0.0, ended - started),
        }

    def _log_event(self, direction: str, file: str, meta: Dict[str, Any], payload: str, task: Optional[str] = None):
        record = {
            "timestamp": int(time.time()),
            "task": task,
            "file": file,
            "direction": direction,
            "prompt_time_sec": meta.get("duration_sec") if direction == "prompt" else None,
            "response_time_sec": meta.get("duration_sec") if direction == "response" else None,
            "bytes": meta["prompt_bytes"] if direction == "prompt" else meta["response_bytes"],
            "chars": meta["prompt_chars"] if direction == "prompt" else meta["response_chars"],
            "words": meta["prompt_words"] if direction == "prompt" else meta["response_words"],
            "sentences": meta["prompt_sentences"] if direction == "prompt" else meta["response_sentences"],
            "loc": meta["response_loc"] if direction == "response" else None,
            "estimated_tokens": meta["prompt_tokens_est"] if direction == "prompt" else meta["response_tokens_est"],
            "payload_preview": payload[:400],
        }
        with self.log_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # --------- ETA helpers ---------
    def historical_eta_sec(self, task_key: str = "description") -> Optional[float]:
        """
        Average response duration for prior runs of this task
        (uses 'task' field written by _log_event; falls back to preview scan).
        """
        if not self.log_file.exists():
            return None
        total = 0.0
        n = 0
        try:
            with self.log_file.open("r", encoding="utf-8") as f:
                for line in f:
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    if obj.get("direction") != "response":
                        continue
                    # Prefer explicit task tag
                    if (obj.get("task") or "").lower() == task_key.lower():
                        dur = obj.get("response_time_sec")
                    else:
                        # Fallback: legacy logs before we had 'task' tag
                        preview = (obj.get("payload_preview") or "").lower()
                        if task_key.lower() not in preview:
                            continue
                        dur = obj.get("response_time_sec")
                    if isinstance(dur, (int, float)) and dur > 0:
                        total += float(dur)
                        n += 1
        except Exception:
            return None
        return (total / n) if n else None


    # ---------------- Testing ----------------
    def generate_testing(self, html: str, seeds: Dict[str, Any]) -> AIResult:
        """
        Produce testing rows for the Testing table.
        Returns CSV-like text (one row per line) with columns:
        Test No., Test Name, Test Description, Lower Limit, Target Value, Upper Limit, Units
        """
        started = time.time()
        prompt = self._build_testing_prompt(html, seeds)

        ok = True
        err = None
        try:
            if (self._client or openai) and os.getenv("OPENAI_API_KEY"):
                response_text = self._call_openai_chat(prompt)
                if not response_text:
                    ok = False
                    err = "Empty response from AI."
                    response_text = self._fallback_stub_testing()
            else:
                response_text = self._fallback_stub_testing()
        except Exception as e:
            ok = False
            err = f"OpenAI error: {e}"
            response_text = self._fallback_stub_testing()

        ended = time.time()
        stats = self._stats(prompt, response_text, started, ended)
        self._log_event(direction="prompt", file="-", meta=stats, payload=prompt, task="testing")
        self._log_event(direction="response", file="-", meta=stats, payload=response_text, task="testing")

        return AIResult(
            ok=ok, text=response_text, error=err,
            prompt_bytes=stats["prompt_bytes"], response_bytes=stats["response_bytes"],
            prompt_chars=stats["prompt_chars"], response_chars=stats["response_chars"],
            prompt_words=stats["prompt_words"], response_words=stats["response_words"],
            prompt_sentences=stats["prompt_sentences"], response_sentences=stats["response_sentences"],
            response_loc=stats["response_loc"],
            prompt_tokens_est=stats["prompt_tokens_est"], response_tokens_est=stats["response_tokens_est"],
            started_at=started, ended_at=ended,
        )

    def _build_testing_prompt(self, html: str, seeds: Dict[str, Any]) -> str:
        pn, title = self._scrape_title(html)

        # Accept either the new single seed ("testing_seed") or the old nested dict.
        testing_seed = (seeds or {}).get("testing_seed", "")
        if not testing_seed:
            old = (seeds or {}).get("testing") or {}
            parts = []
            for k in ("dtp_seed", "atp_seed"):
                v = (old.get(k) or "").strip()
                if v:
                    parts.append(v)
            if parts:
                testing_seed = "\n".join(parts)

        seed_block = f"Guidance:\n{testing_seed}\n" if testing_seed else ""

        return (
            "(task=testing)\n"
            f"Board: {pn} — {title}\n\n"
            "Generate rows for a product Testing table.\n"
            "Output ONLY CSV (no headings, no prose), one row per line, with EXACTLY 7 fields per row:\n"
            "Test No., Test Name, Test Description, Lower Limit, Target Value, Upper Limit, Units\n"
            "Use TN-### style for Test No. Keep fields concise. Leave limits blank if not applicable.\n\n"
            f"{seed_block}"
        )

    def _fallback_stub_testing(self) -> str:
        # CSV rows (no header). Safe default for preview.
        return (
            "TN-001,Safe To Turn On (STTO),Measure resistance between V+ and GND. >100Ω is PASS.,100,,,OHMS\n"
            "TN-002,Gain Check,Apply 10 mVpp at 1 kHz; measure Vout.,,,10,V/V\n"
        )

    # ---------------- FMEA ----------------

    def generate_fmea(self, html: str, seeds: Dict[str, Any]) -> AIResult:
        """
        Produce FMEA rows for the FMEA table.
        Returns CSV-like text (one row per line) with 17 columns matching the UI:
        Item, Potential Failure Mode, Potential Effect of Failure, Severity (1-10),
        Potential Cause(s)/Mechanism(s) of Failure, Occurrence (1-10), Current Process Controls,
        Detection (1-10), RPN, Recommended Action(s), Responsibility, Target Completion Date,
        Actions Taken, Resulting Severity, Resulting Occurrence, Resulting Detection, New RPN
        """
        started = time.time()
        prompt = self._build_fmea_prompt(html, seeds)

        if openai and os.getenv("OPENAI_API_KEY"):
            try:
                response_text = self._call_openai_chat(prompt)
                ok, err = True, None
            except Exception as e:  # pragma: no cover
                response_text = self._fallback_stub_fmea()
                ok, err = False, f"OpenAI error: {e}"
        else:
            response_text = self._fallback_stub_fmea()
            ok, err = True, None

        ended = time.time()
        stats = self._stats(prompt, response_text, started, ended)
        # --- in generate_fmea() ---
        self._log_event("prompt", "-", stats, prompt, task="fmea")
        self._log_event("response", "-", stats, response_text, task="fmea")

        return AIResult(
            ok=ok, text=response_text, error=err,
            prompt_bytes=stats["prompt_bytes"], response_bytes=stats["response_bytes"],
            prompt_chars=stats["prompt_chars"], response_chars=stats["response_chars"],
            prompt_words=stats["prompt_words"], response_words=stats["response_words"],
            prompt_sentences=stats["prompt_sentences"], response_sentences=stats["response_sentences"],
            response_loc=stats["response_loc"],
            prompt_tokens_est=stats["prompt_tokens_est"], response_tokens_est=stats["response_tokens_est"],
            started_at=started, ended_at=ended,
        )

    def _build_fmea_prompt(self, html: str, seeds: Dict[str, Any]) -> str:
        pn, title = self._scrape_title(html)
        fmea_seed = (seeds or {}).get("fmea_seed") or ""
        return (
            f"(task=fmea)\n"
            f"Board: {pn} — {title}\n\n"
            "Generate FMEA rows. Output ONLY CSV (no headings, no prose), one row per line, with EXACTLY 17 fields:\n"
            "Item, Potential Failure Mode, Potential Effect of Failure, Severity (1-10), "
            "Potential Cause(s)/Mechanism(s) of Failure, Occurrence (1-10), Current Process Controls, "
            "Detection (1-10), RPN, Recommended Action(s), Responsibility, Target Completion Date, "
            "Actions Taken, Resulting Severity, Resulting Occurrence, Resulting Detection, New RPN\n"
            "Keep text compact and practical. Use integers for severity/occurrence/detection.\n\n"
            f"Guidance:\n{fmea_seed}\n"
        )

    def _fallback_stub_fmea(self) -> str:
        # 17 CSV columns, no header. Keep it short.
        return (
            "Bias Network,Incorrect bias,Distortion/low gain,6,Tolerance drift,3,Design review,4,72,"
            "Tighten resistor tolerance,Engineer,2025-12-31,,5,3,4,60\n"
        )
