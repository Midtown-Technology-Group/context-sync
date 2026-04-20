from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path

import msal

# Try to import msal_extensions for secure cache on Windows
try:
    import msal_extensions
    HAS_MSAL_EXTENSIONS = True
except ImportError:
    HAS_MSAL_EXTENSIONS = False


def _get_console_window_handle() -> int | None:
    """Get the console window handle for WAM broker auth.
    
    Returns None if not on Windows or unable to get handle.
    In WSL, this attempts to use the Windows console via powershell.
    """
    # Allow override via environment variable
    if "WAM_WINDOW_HANDLE" in os.environ:
        return int(os.environ["WAM_WINDOW_HANDLE"], 0)
    
    # On native Windows, use ctypes to get console window
    if platform.system() == "Windows":
        try:
            import ctypes
            return ctypes.windll.kernel32.GetConsoleWindow()
        except Exception:
            return None
    
    # In WSL, we can't easily get a window handle
    # Return 0 to let MSAL try to find the console automatically
    # or use the foreground window
    if "WSL_DISTRO_NAME" in os.environ or "WSLENV" in os.environ:
        # WSL environment - try to use Windows console via powershell
        try:
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", 
                 "Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public class Win32 { [DllImport(\"kernel32.dll\")] public static extern IntPtr GetConsoleWindow(); }'; [Win32]::GetConsoleWindow()"],
                capture_output=True,
                text=True,
                check=False,
            )
            handle_str = result.stdout.strip()
            if handle_str and handle_str.isdigit():
                return int(handle_str)
        except Exception:
            pass
        return 0  # Let MSAL use foreground window
    
    return None


class GraphAuthSession:
    def __init__(self, config):
        self.config = config
        self.scopes = [
            "User.Read",
            "Calendars.Read",
            "Mail.ReadBasic",
            "Tasks.Read",
            "OnlineMeetings.Read",
            "Chat.Read",
        ]
        
        # Use secure cache on Windows if available, otherwise no persistence
        self.cache, self._cache_persistence = self._create_secure_cache()
        
        # Enable broker (WAM) for Windows SSO
        allow_broker = getattr(config.auth, "allow_broker", True)
        
        self.app = msal.PublicClientApplication(
            client_id=config.client_id,
            authority=f"https://login.microsoftonline.com/{config.tenant_id}",
            token_cache=self.cache,
            allow_broker=allow_broker,
        )

    def _create_secure_cache(self):
        """Create token cache with OS-appropriate secure storage.
        
        Windows: DPAPI-encrypted file (tied to Windows user account)
        Other: Non-persistent in-memory cache (no disk storage)
        """
        if HAS_MSAL_EXTENSIONS and platform.system() == "Windows":
            try:
                # Build cache path in user's profile
                cache_dir = Path.home() / ".config" / "work-context-sync"
                cache_dir.mkdir(parents=True, exist_ok=True)
                cache_path = cache_dir / "token_cache.bin"
                
                # Use DPAPI-encrypted persistence (Windows only)
                persistence = msal_extensions.FilePersistenceWithDataProtection(str(cache_path))
                cache = msal_extensions.PersistedTokenCache(persistence)
                
                print(f"Using DPAPI-encrypted token cache: {cache_path}", file=sys.stderr)
                return cache, persistence
            except Exception as e:
                print(f"Warning: Could not create secure cache ({e}), using in-memory only", file=sys.stderr)
        else:
            if platform.system() == "Windows" and not HAS_MSAL_EXTENSIONS:
                print(
                    "Warning: msal_extensions not installed. "
                    "Install with: pip install msal[broker]\n"
                    "Falling back to in-memory cache (no persistence).",
                    file=sys.stderr
                )
            else:
                print(
                    f"Warning: Secure token cache not available on {platform.system()}. "
                    "Using in-memory cache (no persistence).",
                    file=sys.stderr
                )
        
        # Fallback: non-persistent in-memory cache
        return msal.SerializableTokenCache(), None

    def _load_cache(self) -> None:
        """Handled automatically by PersistedTokenCache if using secure storage."""
        pass

    def _save_cache(self) -> None:
        """Handled automatically by PersistedTokenCache if using secure storage."""
        pass

    def _try_azure_cli_token(self) -> str | None:
        if self.config.auth.mode not in {"auto", "azure-cli"}:
            return None
        try:
            result = subprocess.run(
                [
                    "az",
                    "account",
                    "get-access-token",
                    "--resource-type",
                    "ms-graph",
                    "--query",
                    "accessToken",
                    "-o",
                    "tsv",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        except Exception:
            return None
        token = result.stdout.strip()
        return token or None

    def _try_wam_token(self) -> str | None:
        """Try Windows Web Account Manager (WAM) broker auth.
        
        This uses the Windows identity broker for silent SSO on Entra-joined
        machines. Falls back to interactive browser if broker unavailable.
        """
        if self.config.auth.mode not in {"wam", "auto", "interactive"}:
            return None
        
        accounts = self.app.get_accounts()
        
        # Try silent authentication first (SSO from Windows session)
        if accounts:
            result = self.app.acquire_token_silent_with_error(
                self.scopes, 
                account=accounts[0],
                force_refresh=False,
            )
            if result and "access_token" in result:
                self._save_cache()
                return result["access_token"]
        
        # Try WAM interactive authentication
        try:
            parent_handle = _get_console_window_handle()
            
            # When broker is enabled (allow_broker=True) and parent_window_handle
            # is provided, MSAL will attempt WAM SSO first
            result = self.app.acquire_token_interactive(
                scopes=self.scopes,
                parent_window_handle=parent_handle,
                timeout=300,  # 5 minute timeout
                prompt="select_account" if not accounts else None,
            )
            
            self._save_cache()
            if "access_token" in result:
                return result["access_token"]
                
        except Exception as e:
            # Broker not available or other error - will fall back
            print(f"WAM auth unavailable ({e}), falling back...", file=sys.stderr)
            return None
        
        return None

    def _try_msal_interactive_token(self) -> str | None:
        """Try standard interactive browser auth (fallback)."""
        if self.config.auth.mode not in {"interactive", "auto", "msal", "wam"}:
            return None
        
        accounts = self.app.get_accounts()
        result = None
        
        # Try silent first
        if accounts:
            result = self.app.acquire_token_silent(self.scopes, account=accounts[0])
            if result and "access_token" in result:
                self._save_cache()
                return result["access_token"]
        
        # Browser-based interactive auth
        try:
            result = self.app.acquire_token_interactive(
                scopes=self.scopes,
                timeout=300,
            )
            self._save_cache()
            if "access_token" in result:
                return result["access_token"]
        except Exception as e:
            print(f"Interactive auth failed ({e}), trying device code...", file=sys.stderr)
            return None
        
        return None

    def _try_device_code_token(self) -> str | None:
        """Device code flow as last resort."""
        if self.config.auth.mode not in {"device-code", "auto", "msal", "interactive", "wam"}:
            return None
        
        flow = self.app.initiate_device_flow(scopes=self.scopes)
        if "user_code" not in flow:
            raise RuntimeError("Failed to initiate device code flow")
        print(flow["message"])
        result = self.app.acquire_token_by_device_flow(flow)
        self._save_cache()
        
        if "access_token" in result:
            return result["access_token"]
        return None

    def acquire_token(self) -> str:
        """Acquire Graph access token using available auth methods.
        
        Order of preference:
        1. Azure CLI (if mode=azure-cli)
        2. WAM Broker SSO (if mode=wam on Entra-joined Windows)
        3. Interactive browser auth
        4. Device code flow (last resort)
        """
        # Try Azure CLI if preferred
        token = self._try_azure_cli_token()
        if token:
            return token
        
        # Try WAM broker auth (Windows SSO)
        token = self._try_wam_token()
        if token:
            return token
        
        # Try standard interactive browser auth
        token = self._try_msal_interactive_token()
        if token:
            return token
        
        # Fall back to device code
        token = self._try_device_code_token()
        if token:
            return token
        
        raise RuntimeError(
            "Unable to acquire Microsoft Graph access token. "
            "Tried: WAM broker, interactive browser, device code. "
            "Ensure you're signed in to Windows with your work account, "
            "or run 'az login' for Azure CLI auth."
        )
