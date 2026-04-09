import asyncio
import json
import aiohttp
from config import KIE_API_KEY

API_URL = "https://api.kie.ai/api/v1/jobs/createTask"
TASK_STATUS_URL = "https://api.kie.ai/api/v1/jobs/recordInfo"

POLL_INTERVAL = 4       # секунды между проверками статуса
POLL_MAX_ATTEMPTS = 45  # максимум 45 * 4 = 180 секунд ожидания


class KieError(Exception):
    pass


async def generate_image(image_url: str, prompt: str) -> bytes:
    """
    Отправляет URL фото и промпт в KIE.ai API (модель google/nano-banana).
    Ожидает завершения задачи и возвращает байты результирующего изображения.
    """
    headers = {
        "Authorization": f"Bearer {KIE_API_KEY.strip()}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "google/nano-banana",
        "input": {
            "prompt": prompt,
            "imageUrls": [image_url],
            "resolution": "1K",
        },
    }

    async with aiohttp.ClientSession() as session:
        # Шаг 1: Запускаем генерацию
        async with session.post(
            API_URL, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            data = await resp.json(content_type=None)

        code = data.get("code")
        if code != 200:
            msg = data.get("msg") or data.get("message") or str(data)
            raise KieError(f"KIE.ai вернул ошибку {code}: {msg}")

        task_id = data["data"]["taskId"]

        # Шаг 2: Поллинг статуса задачи
        for _ in range(POLL_MAX_ATTEMPTS):
            await asyncio.sleep(POLL_INTERVAL)

            async with session.get(
                TASK_STATUS_URL,
                params={"taskId": task_id},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as status_resp:
                if status_resp.status != 200:
                    continue
                status_data = await status_resp.json(content_type=None)

            task_data = status_data.get("data") or {}
            state = task_data.get("state", "")

            if state == "success":
                result_json_str = task_data.get("resultJson", "{}")
                result_json = json.loads(result_json_str) if result_json_str else {}
                result_urls = result_json.get("resultUrls") or []
                result_url = result_urls[0] if result_urls else None
                if not result_url:
                    raise KieError("Задача завершена, но resultUrls отсутствует")
                break
            elif state == "fail":
                error_msg = task_data.get("failMsg") or "неизвестная ошибка генерации"
                raise KieError(f"Генерация не удалась: {error_msg}")
        else:
            raise KieError("Превышено время ожидания генерации (3 минуты)")

        # Шаг 3: Скачиваем результирующее изображение
        async with session.get(result_url, timeout=aiohttp.ClientTimeout(total=60)) as img_resp:
            if img_resp.status != 200:
                raise KieError(f"Не удалось скачать результат: HTTP {img_resp.status}")
            result_bytes = await img_resp.read()

    if not result_bytes:
        raise KieError("Получен пустой файл изображения")

    return result_bytes
