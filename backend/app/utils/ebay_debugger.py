#!/usr/bin/env python3
"""
eBay API Debugger - Interactive CLI tool for debugging eBay API requests.

Usage:
    python -m app.utils.ebay_debugger --user-id UUID
    python -m app.utils.ebay_debugger --user-id UUID --template identity
    python -m app.utils.ebay_debugger --user-id UUID --method GET --path /sell/fulfillment/v1/order --params limit=1
"""

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from urllib.parse import urlencode

import httpx

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.config import settings
from app.services.postgres_database import PostgresDatabase
from app.utils.logger import logger

# ANSI color codes for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    RESET = '\033[0m'
    DIM = '\033[2m'


class EbayAPIDebugger:
    """Interactive CLI tool for debugging eBay API requests."""
    
    def __init__(self, user_id: str, raw_mode: bool = False, save_history: bool = True):
        self.user_id = user_id
        self.db = PostgresDatabase()
        self.user = None
        self.access_token = None
        self.base_url = settings.ebay_api_base_url
        self.raw_mode = raw_mode
        self.save_history = save_history
        self.history_dir = Path(__file__).parent.parent.parent / "debug_history"
        self.history_dir.mkdir(exist_ok=True)
        
    def load_user_token(self) -> bool:
        """Load user and access token from database."""
        try:
            self.user = self.db.get_user_by_id(self.user_id)
            if not self.user:
                self._print_error(f"User with ID {self.user_id} not found")
                return False
            
            from app.utils.ebay_token_helper import get_user_ebay_token, is_user_ebay_connected
            
            env = self.user.ebay_environment or "sandbox"
            
            if not is_user_ebay_connected(self.user, env):
                self._print_error(f"User {self.user.email} is not connected to eBay ({env}) or has no access token")
                return False
            
            self.access_token = get_user_ebay_token(self.user, env)
            if not self.access_token:
                self._print_error(f"User {self.user.email} has no access token for {env} environment")
                return False
            
            self._print_success(f"✅ Loaded token for user: {self.user.email}")
            self._print_info(f"   Environment: {env}")
            self._print_info(f"   Base URL: {self.base_url}")
            return True
        except Exception as e:
            self._print_error(f"Error loading user token: {e}")
            logger.error(f"Error loading user token: {e}", exc_info=True)
            return False
    
    def _print_success(self, text: str):
        """Print success message in green."""
        print(f"{Colors.GREEN}{text}{Colors.RESET}")
    
    def _print_error(self, text: str):
        """Print error message in red."""
        print(f"{Colors.RED}{text}{Colors.RESET}")
    
    def _print_warning(self, text: str):
        """Print warning message in yellow."""
        print(f"{Colors.YELLOW}{text}{Colors.RESET}")
    
    def _print_info(self, text: str):
        """Print info message in cyan."""
        print(f"{Colors.CYAN}{text}{Colors.RESET}")
    
    def _print_bold(self, text: str):
        """Print bold text."""
        print(f"{Colors.BOLD}{text}{Colors.RESET}")
    
    def _mask_token(self, token: str) -> str:
        """Mask token for display."""
        if len(token) > 30:
            return token[:15] + "..." + token[-10:]
        return token[:10] + "..."
    
    def save_request_history(self, template_name: str, request_data: Dict[str, Any], 
                            response_data: Dict[str, Any], response_time_ms: float):
        """Save request and response to history file."""
        if not self.save_history:
            return
        
        try:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = f"{timestamp}_{template_name}.json"
            filepath = self.history_dir / filename
            
            history_entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "user_id": self.user_id,
                "user_email": self.user.email if self.user else None,
                "environment": self.user.ebay_environment if self.user else None,
                "template": template_name,
                "request": request_data,
                "response": response_data,
                "response_time_ms": response_time_ms
            }
            
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(history_entry, f, indent=2, ensure_ascii=False)
            
            self._print_info(f"💾 Saved to: {filepath}")
        except Exception as e:
            self._print_warning(f"⚠️  Could not save history: {e}")
    
    def parse_params(self, params_str: Optional[str]) -> Dict[str, str]:
        """Parse query parameters from string like 'key1=value1&key2=value2'."""
        if not params_str:
            return {}
        
        params = {}
        for pair in params_str.split('&'):
            if '=' in pair:
                key, value = pair.split('=', 1)
                params[key.strip()] = value.strip()
        return params
    
    def parse_headers(self, headers_str: Optional[str]) -> Dict[str, str]:
        """Parse headers from string like 'Header1: Value1, Header2: Value2'."""
        if not headers_str:
            return {}
        
        headers = {}
        for pair in headers_str.split(','):
            if ':' in pair:
                key, value = pair.split(':', 1)
                headers[key.strip()] = value.strip()
        return headers
    
    def get_template(self, template_name: str) -> Dict[str, Any]:
        """Get predefined template for quick start."""
        templates = {
            "identity": {
                "name": "Identity API - Get User Info",
                "method": "GET",
                "path": "/identity/v1/oauth2/userinfo",
                "params": {},
                "headers": {},
                "body": None,
                "description": "Get current user identity (username, user_id)"
            },
            "orders": {
                "name": "Orders API - Get Orders",
                "method": "GET",
                "path": "/sell/fulfillment/v1/order",
                "params": {
                    "limit": "1",
                    "filter": "orderStatus:COMPLETED"
                },
                "headers": {},
                "body": None,
                "description": "Get seller orders (Fulfillment API)"
            },
            "transactions": {
                "name": "Transactions API - Get Transactions",
                "method": "GET",
                "path": "/sell/finances/v1/transaction",
                "params": {
                    "limit": "1",
                    "filter": "transactionDate:[2024-01-01T00:00:00.000Z..2024-12-31T23:59:59.999Z]"
                },
                "headers": {},
                "body": None,
                "description": "Get financial transactions (Finances API)"
            },
            "inventory": {
                "name": "Inventory API - Get Inventory Items",
                "method": "GET",
                "path": "/sell/inventory/v1/inventory_item",
                "params": {
                    "limit": "1"
                },
                "headers": {},
                "body": None,
                "description": "Get inventory items"
            },
            "offers": {
                "name": "Offers API - Get Offers",
                "method": "GET",
                "path": "/sell/inventory/v1/offer",
                "params": {
                    "limit": "1"
                },
                "headers": {},
                "body": None,
                "description": "Get offers (Inventory API)"
            },
            "disputes": {
                "name": "Disputes API - Get Payment Disputes",
                "method": "GET",
                "path": "/sell/fulfillment/v1/payment_dispute",
                "params": {
                    "limit": "1"
                },
                "headers": {},
                "body": None,
                "description": "Get payment disputes (Fulfillment API)"
            },
            "messages": {
                "name": "Messages API - Get Messages",
                "method": "GET",
                "path": "/sell/fulfillment/v1/order",
                "params": {
                    "limit": "1"
                },
                "headers": {},
                "body": None,
                "description": "Get messages (Trading API - placeholder)"
            }
        }
        
        return templates.get(template_name.lower())
    
    def print_request(self, method: str, url: str, headers: Dict[str, str], 
                     params: Dict[str, str], body: Optional[str]):
        """Print formatted request details."""
        print(f"\n{Colors.BOLD}{'='*80}{Colors.RESET}")
        print(f"{Colors.BOLD}→ REQUEST{Colors.RESET}")
        print(f"{Colors.BOLD}{'='*80}{Colors.RESET}")
        print(f"{Colors.CYAN}Method:{Colors.RESET} {Colors.BOLD}{method}{Colors.RESET}")
        print(f"{Colors.CYAN}URL:{Colors.RESET} {url}")
        
        if params:
            print(f"\n{Colors.CYAN}Query Parameters:{Colors.RESET}")
            for key, value in params.items():
                print(f"  {Colors.DIM}{key}{Colors.RESET} = {value}")
        
        if headers:
            print(f"\n{Colors.CYAN}Headers:{Colors.RESET}")
            for key, value in headers.items():
                # Mask token in output
                if key.lower() == "authorization" and "Bearer" in value:
                    masked = self._mask_token(value)
                    print(f"  {Colors.DIM}{key}{Colors.RESET}: Bearer {masked}")
                else:
                    print(f"  {Colors.DIM}{key}{Colors.RESET}: {value}")
        
        if body:
            print(f"\n{Colors.CYAN}Body:{Colors.RESET}")
            try:
                body_json = json.loads(body)
                print(json.dumps(body_json, indent=2))
            except:
                print(body)
        
        print(f"{Colors.BOLD}{'='*80}{Colors.RESET}\n")
    
    def print_response(self, response: httpx.Response, response_time_ms: float):
        """Print formatted response details with color coding."""
        status_code = response.status_code
        status_color = Colors.GREEN if 200 <= status_code < 300 else Colors.RED
        
        print(f"\n{Colors.BOLD}{'='*80}{Colors.RESET}")
        print(f"{Colors.BOLD}← RESPONSE{Colors.RESET}")
        print(f"{Colors.BOLD}{'='*80}{Colors.RESET}")
        
        # Status code with emoji
        if 200 <= status_code < 300:
            status_emoji = "🟢"
        elif 400 <= status_code < 500:
            status_emoji = "🔴"
        elif 500 <= status_code < 600:
            status_emoji = "🔴"
        else:
            status_emoji = "🟡"
        
        print(f"{status_emoji} {status_color}Status: {status_code} {response.reason_phrase}{Colors.RESET}")
        print(f"{Colors.CYAN}Response Time:{Colors.RESET} {response_time_ms:.2f} ms")
        
        # eBay-specific headers
        ebay_headers = {k: v for k, v in response.headers.items() 
                       if k.lower().startswith('x-ebay')}
        if ebay_headers:
            print(f"\n{Colors.CYAN}eBay Headers:{Colors.RESET}")
            for key, value in ebay_headers.items():
                print(f"  {Colors.DIM}{key}{Colors.RESET}: {value}")
        
        # All headers
        print(f"\n{Colors.CYAN}Headers:{Colors.RESET}")
        for key, value in response.headers.items():
            if not key.lower().startswith('x-ebay'):  # Already shown above
                print(f"  {Colors.DIM}{key}{Colors.RESET}: {value}")
        
        # Body
        print(f"\n{Colors.CYAN}Body:{Colors.RESET}")
        try:
            response_json = response.json()
            body_str = json.dumps(response_json, indent=2)
            
            # Highlight errors in red
            if status_code >= 400:
                if isinstance(response_json, dict):
                    errors = response_json.get("errors", [])
                    if errors:
                        print(f"{Colors.RED}")
                        for error in errors:
                            if isinstance(error, dict):
                                error_id = error.get("errorId", "")
                                message = error.get("message", "")
                                long_message = error.get("longMessage", "")
                                print(f"  Error ID: {error_id}")
                                print(f"  Message: {message}")
                                if long_message:
                                    print(f"  Details: {long_message}")
                        print(f"{Colors.RESET}")
            
            print(body_str)
        except:
            response_text = response.text
            if len(response_text) > 2000:
                print(response_text[:2000] + f"\n{Colors.DIM}... (truncated, total {len(response_text)} chars){Colors.RESET}")
            else:
                if status_code >= 400:
                    print(f"{Colors.RED}{response_text}{Colors.RESET}")
                else:
                    print(response_text)
        
        print(f"{Colors.BOLD}{'='*80}{Colors.RESET}\n")
    
    async def make_request(self, method: str, path: str, params: Optional[Dict[str, str]] = None,
                          headers: Optional[Dict[str, str]] = None, body: Optional[str] = None) -> httpx.Response:
        """Make HTTP request to eBay API."""
        # Build full URL
        if path.startswith('/'):
            url = f"{self.base_url}{path}"
        elif path.startswith('http'):
            url = path
        else:
            url = f"{self.base_url}/{path}"
        
        # Add query parameters
        if params:
            query_string = urlencode(params)
            url = f"{url}?{query_string}" if query_string else url
        
        # Prepare headers
        if self.raw_mode:
            request_headers = {}
        else:
            request_headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json"
            }
        
        if headers:
            request_headers.update(headers)
        
        # Prepare request data for history
        request_data = {
            "method": method,
            "url": url,
            "headers": {k: (self._mask_token(v) if k.lower() == "authorization" else v) 
                       for k, v in request_headers.items()},
            "params": params or {},
            "body": body
        }
        
        # Print request
        self.print_request(method, url, request_headers, params or {}, body)
        
        # Make request
        start_time = time.time()
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
                if method.upper() == "GET":
                    response = await client.get(url, headers=request_headers)
                elif method.upper() == "POST":
                    response = await client.post(url, headers=request_headers, content=body or "")
                elif method.upper() == "PUT":
                    response = await client.put(url, headers=request_headers, content=body or "")
                elif method.upper() == "DELETE":
                    response = await client.delete(url, headers=request_headers)
                elif method.upper() == "PATCH":
                    response = await client.patch(url, headers=request_headers, content=body or "")
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                
                response_time_ms = (time.time() - start_time) * 1000
                
                # Print response
                self.print_response(response, response_time_ms)
                
                # Prepare response data for history
                try:
                    response_body = response.json()
                except:
                    response_body = response.text[:5000]  # Limit body size
                
                response_data = {
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "body": response_body
                }
                
                return response, response_data, response_time_ms
        except Exception as e:
            response_time_ms = (time.time() - start_time) * 1000
            self._print_error(f"\n❌ Error making request: {e}")
            logger.error(f"Error making request: {e}", exc_info=True)
            raise
    
    def show_menu(self):
        """Show interactive menu."""
        print(f"\n{Colors.BOLD}{'='*80}{Colors.RESET}")
        print(f"{Colors.BOLD}🔧 eBay API Debugger{Colors.RESET}")
        print(f"{Colors.BOLD}{'='*80}{Colors.RESET}")
        print(f"{Colors.CYAN}User:{Colors.RESET} {self.user.email}")
        print(f"{Colors.CYAN}Environment:{Colors.RESET} {self.user.ebay_environment or 'sandbox'}")
        print(f"{Colors.CYAN}Base URL:{Colors.RESET} {self.base_url}")
        print(f"\n{Colors.BOLD}Available Templates:{Colors.RESET}\n")
        
        templates = [
            ("1", "identity", "Identity API - Get User Info"),
            ("2", "orders", "Orders API - Get Orders"),
            ("3", "transactions", "Transactions API - Get Transactions"),
            ("4", "inventory", "Inventory API - Get Inventory Items"),
            ("5", "offers", "Offers API - Get Offers"),
            ("6", "disputes", "Disputes API - Get Payment Disputes"),
            ("7", "custom", "Custom Request (manual input)"),
            ("0", "exit", "Exit")
        ]
        
        for num, key, desc in templates:
            print(f"  {Colors.BOLD}{num}.{Colors.RESET} {desc}")
        
        print()
    
    def interactive_mode(self):
        """Run in interactive mode."""
        while True:
            try:
                self.show_menu()
                choice = input(f"{Colors.CYAN}Select option{Colors.RESET} [0-7]: ").strip()
                
                if choice == "0" or choice.lower() == "exit":
                    self._print_info("👋 Goodbye!")
                    break
                
                if choice == "7" or choice.lower() == "custom":
                    # Custom request
                    method = input(f"{Colors.CYAN}HTTP Method{Colors.RESET} [GET]: ").strip() or "GET"
                    path = input(f"{Colors.CYAN}API Path{Colors.RESET} (e.g., /sell/fulfillment/v1/order): ").strip()
                    if not path:
                        self._print_error("❌ Path is required")
                        continue
                    
                    params_str = input(f"{Colors.CYAN}Query Parameters{Colors.RESET} (key1=value1&key2=value2) [optional]: ").strip()
                    headers_str = input(f"{Colors.CYAN}Additional Headers{Colors.RESET} (Header1: Value1, Header2: Value2) [optional]: ").strip()
                    body_str = input(f"{Colors.CYAN}Request Body{Colors.RESET} (JSON) [optional]: ").strip()
                    
                    params = self.parse_params(params_str) if params_str else {}
                    headers = self.parse_headers(headers_str) if headers_str else {}
                    body = body_str if body_str else None
                    
                    template_name = "custom"
                    description = f"Custom {method} {path}"
                else:
                    # Use template
                    template_map = {
                        "1": "identity",
                        "2": "orders",
                        "3": "transactions",
                        "4": "inventory",
                        "5": "offers",
                        "6": "disputes"
                    }
                    
                    template_key = template_map.get(choice)
                    if not template_key:
                        self._print_error(f"❌ Invalid option: {choice}")
                        continue
                    
                    template = self.get_template(template_key)
                    if not template:
                        self._print_error(f"❌ Unknown template: {template_key}")
                        continue
                    
                    method = template["method"]
                    path = template["path"]
                    params = template["params"].copy()
                    headers = template["headers"].copy()
                    body = template["body"]
                    template_name = template_key
                    description = template["description"]
                    
                    # Show template info
                    self._print_info(f"\n📋 Template: {template['name']}")
                    self._print_info(f"   {description}")
                    
                    # Allow customization
                    customize = input(f"\n{Colors.CYAN}Customize parameters?{Colors.RESET} (y/n) [n]: ").strip().lower()
                    if customize == 'y':
                        current_params = "&".join([f"{k}={v}" for k, v in params.items()])
                        new_params = input(f"{Colors.CYAN}Query Parameters{Colors.RESET} [{current_params}]: ").strip()
                        if new_params:
                            params = self.parse_params(new_params)
                
                # Ask for repeat count
                repeat = input(f"{Colors.CYAN}Repeat N times{Colors.RESET} [1]: ").strip()
                repeat_count = int(repeat) if repeat.isdigit() else 1
                
                # Make request(s)
                for i in range(repeat_count):
                    if repeat_count > 1:
                        self._print_info(f"\n🔄 Request {i+1}/{repeat_count}")
                    
                    try:
                        response, response_data, response_time_ms = asyncio.run(
                            self.make_request(method, path, params, headers, body)
                        )
                        
                        # Save history
                        self.save_request_history(template_name, {
                            "method": method,
                            "path": path,
                            "url": f"{self.base_url}{path}",
                            "params": params,
                            "headers": {k: self._mask_token(v) if k.lower() == "authorization" else v 
                                       for k, v in (headers if self.raw_mode else 
                                                   {**{"Authorization": f"Bearer {self.access_token}"}, **headers}).items()},
                            "body": body
                        }, response_data, response_time_ms)
                        
                        # Quick summary
                        if response.status_code >= 400:
                            self._print_error(f"❌ Request failed with status {response.status_code}")
                        else:
                            self._print_success(f"✅ Request successful")
                        
                    except Exception as e:
                        self._print_error(f"❌ Error: {e}")
                    
                    if repeat_count > 1 and i < repeat_count - 1:
                        wait = input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.RESET}")
                
                # Ask if continue
                if input(f"\n{Colors.CYAN}Make another request?{Colors.RESET} (y/n) [y]: ").strip().lower() == 'n':
                    break
                
            except KeyboardInterrupt:
                print(f"\n\n{Colors.YELLOW}👋 Interrupted. Goodbye!{Colors.RESET}")
                break
            except Exception as e:
                self._print_error(f"\n❌ Error: {e}")
                logger.error(f"Error in interactive mode: {e}", exc_info=True)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="eBay API Debugger - Interactive CLI tool for debugging eBay API requests",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode
  python -m app.utils.ebay_debugger --user-id <UUID>
  
  # Use template
  python -m app.utils.ebay_debugger --user-id <UUID> --template identity
  
  # Manual request
  python -m app.utils.ebay_debugger --user-id <UUID> \\
    --method GET \\
    --path /sell/fulfillment/v1/order \\
    --params "limit=1&filter=orderStatus:COMPLETED"
  
  # Raw mode (no auto-headers)
  python -m app.utils.ebay_debugger --user-id <UUID> --template identity --raw
  
  # Repeat request 5 times
  python -m app.utils.ebay_debugger --user-id <UUID> --template identity --repeat 5
        """
    )
    
    parser.add_argument(
        "--user-id",
        required=True,
        help="User ID (UUID) to get access token for"
    )
    
    parser.add_argument(
        "--template",
        choices=["identity", "orders", "transactions", "inventory", "offers", "disputes", "messages"],
        help="Use predefined template for quick start"
    )
    
    parser.add_argument(
        "--method",
        choices=["GET", "POST", "PUT", "DELETE", "PATCH"],
        default="GET",
        help="HTTP method (default: GET)"
    )
    
    parser.add_argument(
        "--path",
        help="API path (e.g., /sell/fulfillment/v1/order)"
    )
    
    parser.add_argument(
        "--params",
        help="Query parameters as string (e.g., 'limit=1&filter=orderStatus:COMPLETED')"
    )
    
    parser.add_argument(
        "--headers",
        help="Additional headers as string (e.g., 'X-EBAY-C-MARKETPLACE-ID: EBAY_US')"
    )
    
    parser.add_argument(
        "--body",
        help="Request body (JSON string)"
    )
    
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Raw mode: don't add auto-headers (Authorization, Accept, Content-Type)"
    )
    
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Don't save request history to files"
    )
    
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Repeat request N times (default: 1)"
    )
    
    args = parser.parse_args()
    
    # Create debugger
    debugger = EbayAPIDebugger(
        args.user_id, 
        raw_mode=args.raw,
        save_history=not args.no_save
    )
    
    # Load user token
    if not debugger.load_user_token():
        sys.exit(1)
    
    # Run in template/CLI mode or interactive mode
    if args.template or args.path:
        # Non-interactive mode
        if args.template:
            template = debugger.get_template(args.template)
            if not template:
                print(f"❌ Unknown template: {args.template}")
                sys.exit(1)
            
            method = args.method or template["method"]
            path = args.path or template["path"]
            params = debugger.parse_params(args.params) if args.params else template["params"]
            headers = debugger.parse_headers(args.headers) if args.headers else template["headers"]
            body = args.body or template["body"]
        else:
            method = args.method
            path = args.path
            params = debugger.parse_params(args.params) if args.params else {}
            headers = debugger.parse_headers(args.headers) if args.headers else {}
            body = args.body
        
        if not path:
            print("❌ Path is required when not using interactive mode")
            sys.exit(1)
        
        # Repeat requests
        for i in range(args.repeat):
            if args.repeat > 1:
                debugger._print_info(f"\n🔄 Request {i+1}/{args.repeat}")
            
            try:
                response, response_data, response_time_ms = asyncio.run(
                    debugger.make_request(method, path, params, headers, body)
                )
                
                # Save history
                template_name = args.template or "manual"
                debugger.save_request_history(template_name, {
                    "method": method,
                    "path": path,
                    "url": f"{debugger.base_url}{path}",
                    "params": params,
                    "headers": {k: debugger._mask_token(v) if k.lower() == "authorization" else v 
                               for k, v in (headers if args.raw else 
                                           {**{"Authorization": f"Bearer {debugger.access_token}"}, **headers}).items()},
                    "body": body
                }, response_data, response_time_ms)
                
            except Exception as e:
                debugger._print_error(f"❌ Error: {e}")
                if i < args.repeat - 1:
                    import time
                    time.sleep(1)  # Brief pause between retries
    else:
        # Interactive mode
        debugger.interactive_mode()


if __name__ == "__main__":
    main()
