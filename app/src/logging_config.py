




import logging
import sys
import time
from pathlib import Path
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from config import LOG_LEVEL, LOG_FILE

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

def setup_logging() -> None:





    log_path = Path(LOG_FILE)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    level = getattr(logging, LOG_LEVEL, logging.INFO)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    root_logger.handlers.clear()
    
    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    
    file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    
    logging.getLogger(__name__).info(f"Logging configured: level={LOG_LEVEL}, file={LOG_FILE}")

def get_logger(name: str) -> logging.Logger:








    return logging.getLogger(name)

class RequestLoggingMiddleware(BaseHTTPMiddleware):




    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:









        logger = get_logger("http")
        
        if request.url.path == "/health":
            return await call_next(request)
        
        start_time = time.perf_counter()
        
        response = await call_next(request)
        
        duration = time.perf_counter() - start_time
        
        logger.info(
            f"{request.method} {request.url.path} {response.status_code} {duration:.3f}s"
        )
        
        return response
