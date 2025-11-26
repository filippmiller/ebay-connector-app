"""Worker-level configuration for background analytics and automation workers.

This module mirrors the settings previously located under
``app.config.worker_settings`` but is defined as a top-level module so that
it can be imported without requiring ``app.config`` to be a package.
"""

from app.config import settings  # re-use global Settings if needed in future

# Minimum desired profit margin per computer (in the same currency units as
# expected_profit). The model profitability and monitoring workers use this to
# derive max_buy_price and filter profitable models.
MIN_PROFIT_MARGIN: float = 40.0

# --- Auto-Offer / Auto-Buy planner settings ---

# When True, the auto-offer/buy worker only plans actions (writes ai_ebay_actions
# in 'draft' status) and NEVER calls real eBay APIs.
AUTO_BUY_DRY_RUN: bool = True

# Minimum required ROI (predicted_profit / total_price) for a candidate to be
# considered for auto-offer/auto-buy.
AUTO_BUY_MIN_ROI: float = 0.30  # 30%

# Minimum absolute predicted profit required for a candidate to be considered
# for auto-offer/auto-buy.
AUTO_BUY_MIN_PROFIT: float = 40.0  # currency units
