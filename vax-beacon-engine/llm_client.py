"""
LLM Client Abstraction Layer
==============================
Swappable backend: Anthropic Claude (local) → MedGemma 4B (local RTX 4050)
"""

import gc
import json
import re
import time
import numpy as np
from config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, MAX_TOKENS, TEMPERATURE


# --- Custom JSON encoder for numpy types ---
class _NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


# --- StopOnJsonClose: stop generation when top-level JSON object closes ---
class _StopOnJsonClose:
    """Transformers StoppingCriteria: halt when brace depth returns to 0."""

    def __init__(self, tokenizer, prompt_len: int):
        self.tokenizer = tokenizer
        self.prompt_len = prompt_len

    def __call__(self, input_ids, scores, **kwargs):
        import torch
        generated = input_ids[0][self.prompt_len:]
        text = self.tokenizer.decode(generated, skip_special_tokens=True)
        # Start at depth=1 because the pre-filled opening '{' is in the prompt
        depth = 1
        for ch in text:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return True
        return False


class _TimeLimitCriteria:
    """Transformers StoppingCriteria: halt generation if wall-clock time exceeds limit.

    This stops model.generate() from the INSIDE, preventing zombie CUDA threads
    that occur when using external thread.join(timeout) to kill long-running generation.
    """

    def __init__(self, max_seconds: float = 120.0):
        self._max_seconds = max_seconds
        self._start_time = time.monotonic()

    def __call__(self, input_ids, scores, **kwargs):
        return (time.monotonic() - self._start_time) >= self._max_seconds


class LLMClient:
    """
    Unified LLM interface.
    - Local: Anthropic Claude API
    - MedGemma: google/medgemma-1.5-4b-it with 4-bit quantization
    """

    # Stage-specific token budgets (stability-first)
    STAGE_TOKENS = {
        "stage1": 2048,
        "stage3a": 1536,
        "stage3c": 1024,
        "stage5": 1536,
        "stage6": 1536,
        "query_light": 256,
    }

    def __init__(self, backend="anthropic"):
        self.backend = backend
        if backend == "anthropic":
            import anthropic
            self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        elif backend == "medgemma":
            self._load_medgemma()
        else:
            raise ValueError(f"Unknown backend: {backend}")

    # ------------------------------------------------------------------
    #  MedGemma initialization
    # ------------------------------------------------------------------
    def _load_medgemma(self):
        import torch
        from transformers import AutoModelForImageTextToText, AutoProcessor, BitsAndBytesConfig

        model_id = "google/medgemma-1.5-4b-it"
        print(f"  [MedGemma] Loading {model_id} with 4-bit quantization...")

        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
        )

        # Attention implementation: prefer FA2, fallback to SDPA
        attn_impl = "sdpa"
        if torch.cuda.get_device_capability()[0] >= 8:
            try:
                import flash_attn  # noqa: F401
                attn_impl = "flash_attention_2"
            except ImportError:
                pass
        self._attn_impl = attn_impl
        print(f"  [MedGemma] Attention: {attn_impl}")

        self.model = AutoModelForImageTextToText.from_pretrained(
            model_id,
            quantization_config=bnb_config,
            device_map="auto",
            attn_implementation=attn_impl,
        )

        self.processor = AutoProcessor.from_pretrained(model_id)
        self.tokenizer = self.processor.tokenizer

        # Cache thinking-token id (<unused94>) for suppression
        self._thinking_token_id = None
        try:
            tid = self.tokenizer.convert_tokens_to_ids("<unused94>")
            if tid != self.tokenizer.unk_token_id:
                self._thinking_token_id = tid
        except Exception:
            pass

        mem_used = torch.cuda.memory_allocated() / 1e9
        mem_total = torch.cuda.get_device_properties(0).total_memory / 1e9
        print(f"  [MedGemma] VRAM: {mem_used:.1f} / {mem_total:.1f} GB ({mem_used/mem_total*100:.0f}%)")
        print(f"  [MedGemma] Ready.\n")

    # ------------------------------------------------------------------
    #  Stage detection from system prompt
    # ------------------------------------------------------------------
    @staticmethod
    def _detect_stage(system_prompt: str) -> str:
        sp = system_prompt.lower()
        if "icsr" in sp or "stage 1" in sp or "stage1" in sp:
            return "stage1"
        if "clinical observer" in sp or "stage 3a" in sp or "stage3a" in sp:
            return "stage3a"
        if "plausibility" in sp or "stage 3c" in sp or "stage3c" in sp:
            return "stage3c"
        if "causality" in sp or "stage 5" in sp or "stage5" in sp:
            return "stage5"
        if "guidance" in sp or "stage 6" in sp or "stage6" in sp:
            return "stage6"
        return "default"

    # ------------------------------------------------------------------
    #  JSON repair utilities
    # ------------------------------------------------------------------
    @staticmethod
    def _repair_json(text: str) -> str:
        """Best-effort repair of common MedGemma JSON issues."""
        s = text
        # 0. Strip control characters (except \n \r \t) that break json.loads
        s = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', s)
        # 1. Remove JavaScript-style // comments (MedGemma sometimes adds them)
        s = re.sub(r'//[^\n]*', '', s)
        # 2. Strip ALL backslash escapes that aren't valid JSON.
        #    Valid: \" \\ \/ \b \f \n \r \t \uXXXX
        #    Invalid: \_ \. \{ \} \- \( \) \* \# etc. → remove backslash
        s = re.sub(r'\\(?!["\\/bfnrtu])', '', s)
        # 3. Fix ">= null" → null  (garbled comparison operators)
        s = re.sub(r'">?=\s*null', 'null', s)
        # 4. Trailing commas before } or ]
        s = re.sub(r",\s*([}\]])", r"\1", s)
        # 5. Single-quoted keys/values → double-quoted
        s = re.sub(r"(?<=[\{,\[])\s*'([^']+?)'\s*:", r' "\1":', s)
        s = re.sub(r":\s*'([^']*?)'\s*(?=[,\}\]])", r': "\1"', s)
        return s

    @staticmethod
    def _unwrap_list(parsed):
        """If LLM returned a JSON array, unwrap the first dict element."""
        if isinstance(parsed, list) and len(parsed) > 0 and isinstance(parsed[0], dict):
            return parsed[0]
        return parsed

    @staticmethod
    def _extract_json_object(text: str) -> str:
        """Extract the first complete top-level JSON object from text."""
        start = text.find("{")
        if start == -1:
            return text
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        # Unclosed — return from start to end and append closing braces
        return text[start:] + "}" * depth if depth > 0 else text[start:]

    # ------------------------------------------------------------------
    #  Core MedGemma generation
    # ------------------------------------------------------------------
    # Per-call time limit (seconds) for model.generate()
    GENERATE_TIME_LIMIT = 120.0

    def _generate_medgemma(self, system_prompt: str, user_message: str,
                           max_new_tokens: int, temperature: float,
                           prefill_brace: bool = False) -> str:
        import torch
        from transformers import StoppingCriteriaList

        # MedGemma chat template folds system into user turn automatically.
        # Use system role so the template handles formatting.
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        text = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )

        # Pre-fill with opening brace to force JSON output
        if prefill_brace:
            text += "{"

        inputs = self.tokenizer(text, return_tensors="pt").to(self.model.device)
        prompt_len = inputs["input_ids"].shape[-1]

        # Build generation kwargs
        gen_kwargs = {
            "max_new_tokens": max_new_tokens,
            "pad_token_id": self.tokenizer.eos_token_id,
            "do_sample": temperature > 0,
            "repetition_penalty": 1.3,
            "no_repeat_ngram_size": 4,
        }
        if temperature > 0:
            gen_kwargs["temperature"] = temperature

        # Suppress thinking token
        if self._thinking_token_id is not None:
            gen_kwargs["bad_words_ids"] = [[self._thinking_token_id]]

        # Stopping criteria: always include time limit + optional JSON close
        criteria = [_TimeLimitCriteria(max_seconds=self.GENERATE_TIME_LIMIT)]
        if prefill_brace:
            criteria.append(_StopOnJsonClose(self.tokenizer, prompt_len))
        gen_kwargs["stopping_criteria"] = StoppingCriteriaList(criteria)

        t0 = time.monotonic()
        with torch.no_grad():
            output = self.model.generate(**inputs, **gen_kwargs)
        elapsed = time.monotonic() - t0

        result = self.tokenizer.decode(
            output[0][prompt_len:], skip_special_tokens=True
        )

        # Prepend the brace we pre-filled
        if prefill_brace:
            result = "{" + result

        # Cleanup VRAM
        del inputs, output
        torch.cuda.empty_cache()

        # If time limit was hit, raise so caller can handle gracefully
        if elapsed >= self.GENERATE_TIME_LIMIT - 1.0:
            raise TimeoutError(
                f"MedGemma generation exceeded {self.GENERATE_TIME_LIMIT}s "
                f"(actual: {elapsed:.1f}s). Partial output discarded."
            )

        return result.strip()

    # ------------------------------------------------------------------
    #  Public API: query()
    # ------------------------------------------------------------------
    def query(self, system_prompt: str, user_message: str, temperature: float = None) -> str:
        """Send a query and return the text response."""
        temp = temperature if temperature is not None else TEMPERATURE

        if self.backend == "anthropic":
            import anthropic
            response = self.client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=MAX_TOKENS,
                temperature=temp,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            return response.content[0].text

        elif self.backend == "medgemma":
            stage = self._detect_stage(system_prompt)
            tokens = self.STAGE_TOKENS.get(stage, 1024)
            return self._generate_medgemma(
                system_prompt, user_message, tokens, temp, prefill_brace=True
            )

    # ------------------------------------------------------------------
    #  Public API: query_light()
    # ------------------------------------------------------------------
    def query_light(self, system_prompt: str, user_message: str) -> str:
        """Lightweight query (Haiku for Anthropic, reduced tokens for MedGemma)."""
        if self.backend == "anthropic":
            import anthropic
            from config import ANTHROPIC_MODEL_LIGHT
            response = self.client.messages.create(
                model=ANTHROPIC_MODEL_LIGHT,
                max_tokens=256,
                temperature=0.0,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            return response.content[0].text.strip()

        elif self.backend == "medgemma":
            return self._generate_medgemma(
                system_prompt, user_message, 256, 0.0, prefill_brace=False
            )

    # ------------------------------------------------------------------
    #  Public API: query_text() — plain text only, no JSON parsing
    # ------------------------------------------------------------------
    def query_text(self, system_prompt: str, user_message: str, temperature: float = None) -> str:
        """Send a query and return the raw text response (no JSON parsing).
        Used by MedGemma hybrid stages where LLM only fills short text fields."""
        temp = temperature if temperature is not None else TEMPERATURE

        if self.backend == "anthropic":
            import anthropic
            response = self.client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=MAX_TOKENS,
                temperature=temp,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            return response.content[0].text.strip()

        elif self.backend == "medgemma":
            stage = self._detect_stage(system_prompt)
            tokens = min(self.STAGE_TOKENS.get(stage, 512), 512)
            return self._generate_medgemma(
                system_prompt, user_message, tokens, temp, prefill_brace=False
            )

    # ------------------------------------------------------------------
    #  Public API: query_json()
    # ------------------------------------------------------------------
    def query_json(self, system_prompt: str, user_message: str, temperature: float = None) -> dict:
        """Send a query and parse the response as JSON.

        Robustness strategy (3-layer):
          1. Parse raw → extract JSON object → repair → parse
          2. On failure: retry with "Respond ONLY with valid JSON" hint (up to 3 attempts)
          3. On all failures: return empty dict instead of raising (pipeline continues)
        """
        max_attempts = 3 if self.backend == "medgemma" else 1
        last_error = None
        last_raw = ""

        for attempt in range(max_attempts):
            try:
                # On retry, append JSON-enforcement hint
                if attempt > 0:
                    msg = (
                        user_message
                        + "\n\nIMPORTANT: Respond ONLY with valid JSON. "
                        "No comments, no explanation, no markdown."
                    )
                else:
                    msg = user_message

                raw = self.query(system_prompt, msg, temperature)
                last_raw = raw

                # Extract JSON from response (handle markdown code blocks)
                text = raw.strip()
                if text.startswith("```json"):
                    text = text[7:]
                if text.startswith("```"):
                    text = text[3:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()

                # MedGemma: always apply repair first (backslash escapes are pervasive)
                if self.backend == "medgemma":
                    text = self._repair_json(text)

                # Try direct parse (strict=False tolerates control chars in strings)
                try:
                    parsed = json.loads(text, strict=False)
                    parsed = self._unwrap_list(parsed)
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    pass

                # Try extracting JSON object
                extracted = self._extract_json_object(text)
                try:
                    parsed = json.loads(extracted, strict=False)
                    parsed = self._unwrap_list(parsed)
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    pass

                # Try repair again on extracted portion
                repaired = self._repair_json(extracted)
                try:
                    parsed = json.loads(repaired, strict=False)
                    parsed = self._unwrap_list(parsed)
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError as e:
                    last_error = e

            except (TimeoutError, Exception) as e:
                # LLM call itself failed (timeout, CUDA error, etc.)
                last_error = e

            # Retry cleanup
            if attempt < max_attempts - 1:
                gc.collect()
                continue

        # All attempts exhausted — return empty dict (pipeline continues)
        # Caller stages handle empty dict gracefully via .get() defaults
        import logging
        logging.getLogger("vax_beacon_batch").warning(
            f"query_json failed after {max_attempts} attempts: {last_error}. "
            f"Raw[:200]: {last_raw[:200]}"
        )
        return {}
