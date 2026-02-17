"""
LLM Client Abstraction Layer
==============================
Swappable backend: Anthropic Claude (local) → MedGemma 4B (Kaggle)
"""

import json
import anthropic
from config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, MAX_TOKENS, TEMPERATURE


class LLMClient:
    """
    Unified LLM interface.
    - Local: Anthropic Claude API
    - Kaggle: Replace with MedGemma 4B inference
    """

    def __init__(self, backend="anthropic"):
        self.backend = backend
        if backend == "anthropic":
            self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        elif backend == "medgemma":
            # TODO: Kaggle MedGemma 4B initialization
            # from transformers import AutoModelForCausalLM, AutoTokenizer
            # self.model = AutoModelForCausalLM.from_pretrained("google/medgemma-4b-it")
            # self.tokenizer = AutoTokenizer.from_pretrained("google/medgemma-4b-it")
            raise NotImplementedError("MedGemma backend - implement for Kaggle notebook")
        else:
            raise ValueError(f"Unknown backend: {backend}")

    def query(self, system_prompt: str, user_message: str, temperature: float = None) -> str:
        """Send a query and return the text response."""
        temp = temperature if temperature is not None else TEMPERATURE

        if self.backend == "anthropic":
            response = self.client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=MAX_TOKENS,
                temperature=temp,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            return response.content[0].text

        elif self.backend == "medgemma":
            # TODO: MedGemma inference
            raise NotImplementedError

    def query_light(self, system_prompt: str, user_message: str) -> str:
        """Send a query using the lightweight model (Haiku). For summaries only."""
        if self.backend == "anthropic":
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
            # Use same model for light queries in MedGemma backend
            raise NotImplementedError

    def query_json(self, system_prompt: str, user_message: str, temperature: float = None) -> dict:
        """Send a query and parse the response as JSON."""
        raw = self.query(system_prompt, user_message, temperature)

        # Extract JSON from response (handle markdown code blocks)
        text = raw.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            # Attempt to find JSON object in response
            start = text.find("{")
            end = text.rfind("}") + 1
            if start != -1 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
            raise ValueError(f"Failed to parse JSON from LLM response: {e}\nRaw: {raw[:500]}")
