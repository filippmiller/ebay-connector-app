"""Offer normalization parser for eBay API responses"""
from datetime import datetime
from typing import Dict, List, Optional, Any
from decimal import Decimal


def normalize_offer(ebay_offer: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize eBay offer data to our schema.
    
    Returns dict with:
        - offer: dict for Offer table
        - actions: list of dicts for OfferActionLog table (optional)
    """
    offer_id = ebay_offer.get('offerId') or ebay_offer.get('offer_id') or ebay_offer.get('id')
    
    direction = _parse_direction(ebay_offer)
    state = _parse_state(ebay_offer)
    
    price_val, price_cur = _parse_money(ebay_offer.get('price') or ebay_offer.get('amount'))
    orig_val, orig_cur = _parse_money(ebay_offer.get('originalPrice') or ebay_offer.get('listingPrice'))
    
    created_at = _parse_datetime(ebay_offer.get('creationDate') or ebay_offer.get('created_at'))
    expires_at = _parse_datetime(ebay_offer.get('expirationDate') or ebay_offer.get('expires_at'))
    
    offer_data = {
        'offer_id': str(offer_id),
        'direction': direction,
        'state': state,
        'item_id': ebay_offer.get('itemId') or ebay_offer.get('item_id'),
        'sku': ebay_offer.get('sku'),
        'buyer_username': ebay_offer.get('buyer', {}).get('username') if isinstance(ebay_offer.get('buyer'), dict) else ebay_offer.get('buyer_username'),
        'quantity': int(ebay_offer.get('quantity', 1)),
        'price_value': price_val,
        'price_currency': price_cur,
        'original_price_value': orig_val,
        'original_price_currency': orig_cur,
        'created_at': created_at,
        'expires_at': expires_at,
        'message': ebay_offer.get('message') or ebay_offer.get('buyerMessage') or ebay_offer.get('note'),
        'raw_payload': ebay_offer
    }
    
    actions = []
    if 'history' in ebay_offer or 'actions' in ebay_offer:
        history = ebay_offer.get('history') or ebay_offer.get('actions') or []
        for event in history:
            action_data = {
                'offer_id': str(offer_id),
                'action': _parse_action(event.get('action') or event.get('type')),
                'actor': _parse_actor(event.get('actor') or event.get('source')),
                'notes': event.get('notes') or event.get('message'),
                'result_state': _parse_state(event.get('resultingState') or event.get('new_state')),
                'raw_payload': event,
                'created_at': _parse_datetime(event.get('timestamp') or event.get('created_at'))
            }
            actions.append(action_data)
    
    return {
        'offer': offer_data,
        'actions': actions
    }


def _parse_direction(data: Dict) -> str:
    """Parse offer direction"""
    direction = data.get('direction') or data.get('type') or ''
    direction = str(direction).upper()
    
    if 'INBOUND' in direction or 'BUYER' in direction or 'INCOMING' in direction:
        return 'INBOUND'
    if 'OUTBOUND' in direction or 'SELLER' in direction or 'OUTGOING' in direction or 'SENT' in direction:
        return 'OUTBOUND'
    
    if data.get('buyer'):
        return 'INBOUND'
    
    return 'INBOUND'


def _parse_state(data: Dict) -> str:
    """Parse offer state"""
    if not data:
        return 'PENDING'
    
    state = data.get('state') or data.get('status') or ''
    state = str(state).upper()
    
    valid_states = ['PENDING', 'ACCEPTED', 'DECLINED', 'EXPIRED', 'WITHDRAWN', 'COUNTERED', 'SENT']
    
    for valid in valid_states:
        if valid in state:
            return valid
    
    if 'ACCEPT' in state or 'APPROVE' in state:
        return 'ACCEPTED'
    if 'DECLINE' in state or 'REJECT' in state:
        return 'DECLINED'
    if 'EXPIRE' in state or 'TIMEOUT' in state:
        return 'EXPIRED'
    if 'WITHDRAW' in state or 'CANCEL' in state:
        return 'WITHDRAWN'
    if 'COUNTER' in state:
        return 'COUNTERED'
    
    return 'PENDING'


def _parse_action(action_str: Optional[str]) -> str:
    """Parse action type"""
    if not action_str:
        return 'SEND'
    
    action = str(action_str).upper()
    
    valid_actions = ['SEND', 'ACCEPT', 'DECLINE', 'COUNTER', 'EXPIRE', 'WITHDRAW']
    
    for valid in valid_actions:
        if valid in action:
            return valid
    
    return 'SEND'


def _parse_actor(actor_str: Optional[str]) -> str:
    """Parse actor"""
    if not actor_str:
        return 'SYSTEM'
    
    actor = str(actor_str).upper()
    
    if 'ADMIN' in actor or 'SELLER' in actor or 'MANUAL' in actor:
        return 'ADMIN'
    
    return 'SYSTEM'


def _parse_money(money_obj: Optional[Dict]) -> tuple[Optional[Decimal], Optional[str]]:
    """Parse money object to (value, currency)"""
    if not money_obj:
        return None, None
    
    if isinstance(money_obj, (int, float, Decimal)):
        return Decimal(str(money_obj)), None
    
    if not isinstance(money_obj, dict):
        return None, None
    
    value = money_obj.get('value') or money_obj.get('amount')
    currency = money_obj.get('currency') or money_obj.get('currencyId')
    
    if value is not None:
        try:
            return Decimal(str(value)), str(currency)[:3] if currency else None
        except:
            return None, None
    
    return None, None


def _parse_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO datetime string"""
    if not dt_str:
        return None
    
    if isinstance(dt_str, datetime):
        return dt_str
    
    try:
        return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    except:
        try:
            return datetime.strptime(dt_str, '%Y-%m-%dT%H:%M:%S.%fZ')
        except:
            return None
