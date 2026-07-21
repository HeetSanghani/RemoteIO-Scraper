from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import requests
from app.utils.logger import logger


def retry_request(max_attempts=3):
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((requests.exceptions.RequestException,)),
        before_sleep=lambda retry_state: logger.warning(
            f"Retrying... attempt {retry_state.attempt_number}"
        )
    )