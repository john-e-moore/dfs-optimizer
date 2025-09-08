import logging
from typing import Optional


def setup_logger(name: str = "dfs_optimizer", level: int = logging.INFO) -> logging.Logger:
    """Create and configure a logger with a consistent formatter and stream handler.

    Parameters
    ----------
    name: str
        Logger name.
    level: int
        Logging level.

    Returns
    -------
    logging.Logger
        Configured logger instance.
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        logger.setLevel(level)
        return logger

    logger.setLevel(level)
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger
