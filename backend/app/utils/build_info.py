"""
Build information for tracking deployments.

This module provides build number/version information that is logged
at startup and in key operations to verify code deployments.
"""

import os
import subprocess
from datetime import datetime
from typing import Optional

# Build number - can be set via environment variable BUILD_NUMBER
# If not set, will try to get from git commit hash
_BUILD_NUMBER: Optional[str] = None


def get_build_number() -> str:
    """
    Get the current build number.
    
    Priority:
    1. BUILD_NUMBER environment variable
    2. Git commit hash (short, 7 chars)
    3. Timestamp-based fallback
    
    Returns:
        Build number string (e.g., "abc1234" or "20251204-180530")
    """
    global _BUILD_NUMBER
    
    if _BUILD_NUMBER:
        return _BUILD_NUMBER
    
    # Try environment variable first
    build_num = os.getenv("BUILD_NUMBER")
    if build_num:
        _BUILD_NUMBER = build_num
        return build_num
    
    # Try git commit hash
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=7", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        )
        if result.returncode == 0:
            commit_hash = result.stdout.strip()
            if commit_hash:
                _BUILD_NUMBER = commit_hash
                return commit_hash
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        pass
    
    # Fallback to timestamp
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    _BUILD_NUMBER = timestamp
    return timestamp


def get_build_info() -> dict:
    """
    Get full build information.
    
    Returns:
        Dict with build_number, timestamp, and other info
    """
    return {
        "build_number": get_build_number(),
        "timestamp": datetime.now().isoformat(),
    }


# Initialize on import
_BUILD_NUMBER = get_build_number()

