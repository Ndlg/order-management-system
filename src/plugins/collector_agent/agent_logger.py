# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
from datetime import datetime

from .agent_config import ensure_runtime_dirs, logs_dir


def setup_logger(name: str = "OrderCollectorAgent") -> logging.Logger:
    ensure_runtime_dirs()
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    log_path = logs_dir() / f"{datetime.now():%Y%m%d_%H%M%S}.log"
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)
    logger.info("logger_started path=%s", log_path)
    return logger
