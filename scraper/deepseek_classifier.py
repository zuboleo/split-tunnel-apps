from __future__ import annotations

import os
import re
from dataclasses import dataclass

import requests

_ROUTE_RE = re.compile(r"\b(DIRECT|PROXY)\b", re.IGNORECASE)


@dataclass(slots=True)
class DeepSeekClassifier:
    api_key: str
    model: str = "deepseek-chat"
    base_url: str = "https://api.deepseek.com/v1"
    timeout: int = 45

    @classmethod
    def from_env(cls) -> "DeepSeekClassifier":
        api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is not configured")
        return cls(
            api_key=api_key,
            model=os.environ.get("DEEPSEEK_MODEL", "deepseek-chat").strip() or "deepseek-chat",
            base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1").rstrip("/"),
        )

    @staticmethod
    def parse_route(value: str) -> str:
        match = _ROUTE_RE.search(value or "")
        if not match:
            raise ValueError("DeepSeek returned neither DIRECT nor PROXY")
        return match.group(1).upper()

    def classify(self, package_id: str, app_name: str | None, contexts: list[str]) -> str:
        if not contexts:
            raise ValueError("No VPN contexts to classify")

        numbered = "\n".join(f"{index + 1}. {text}" for index, text in enumerate(contexts))
        prompt = (
            "Определи маршрут Android-приложения только по приведенным фрагментам.\n"
            "DIRECT: приложение конфликтует с VPN, не работает с VPN, обнаруживает VPN "
            "или требует его отключить.\n"
            "PROXY: приложению/сервису нужен VPN для нормальной работы или доступа, "
            "без VPN оно не работает/ограничено, либо после включения VPN начинает работать.\n"
            "Учитывай смысл всех фрагментов вместе, а не отдельные ключевые слова. "
            "Ответь РОВНО одним словом: DIRECT или PROXY.\n\n"
            f"package_id: {package_id}\n"
            f"name: {app_name or package_id}\n"
            f"contexts:\n{numbered}"
        )

        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "temperature": 0,
                "messages": [
                    {
                        "role": "system",
                        "content": "Ты классификатор маршрутизации приложений. Возвращай только DIRECT или PROXY.",
                    },
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        content = payload["choices"][0]["message"]["content"]
        return self.parse_route(content)
