"""
LDAP integration service for user synchronization and authentication.
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

try:
    from ldap3 import Server, Connection, ALL, SUBTREE, SIMPLE, BIND_SASL
    from ldap3.core.exceptions import LDAPException, LDAPBindError
    HAS_LDAP3 = True
except ImportError:
    HAS_LDAP3 = False
    logger.warning("ldap3 not installed. LDAP features disabled.")


class LDAPService:
    """Service for LDAP user synchronization and authentication."""
    
    def __init__(self):
        self.server = None
        self.connection = None
    
    def _get_server(self, server_url: str) -> Optional[Server]:
        """Create LDAP server object."""
        if not HAS_LDAP3 or not server_url:
            return None
        try:
            return Server(server_url, get_info=ALL)
        except Exception as e:
            logger.error(f"Failed to create LDAP server: {e}")
            return None
    
    def _get_connection(self, server, bind_dn: str, bind_password: str) -> Optional[Connection]:
        """Create authenticated LDAP connection."""
        if not HAS_LDAP3 or not server:
            return None
        try:
            conn = Connection(
                server,
                user=bind_dn,
                password=bind_password,
                authentication=SIMPLE,
                auto_bind=True
            )
            return conn
        except LDAPBindError as e:
            logger.error(f"LDAP bind failed: {e}")
            return None
        except LDAPException as e:
            logger.error(f"LDAP connection error: {e}")
            return None
    
    async def test_connection(
        self, 
        server_url: str, 
        base_dn: str, 
        bind_dn: str, 
        bind_password: str
    ) -> Dict[str, Any]:
        """Test LDAP connection and return status."""
        if not HAS_LDAP3:
            return {"success": False, "error": "ldap3 not installed"}
        
        server = self._get_server(server_url)
        if not server:
            return {"success": False, "error": "Invalid server URL"}
        
        conn = self._get_connection(server, bind_dn, bind_password)
        if not conn:
            return {"success": False, "error": "Authentication failed"}
        
        # Try a search to verify connectivity
        try:
            conn.search(
                search_base=base_dn,
                search_filter="(objectClass=*)",
                search_scope=SUBTREE,
                attributes=['cn']
            )
            conn.unbind()
            return {"success": True, "message": "Connection successful"}
        except Exception as e:
            return {"success": False, "error": f"Search failed: {str(e)}"}
    
    async def sync_users(
        self,
        server_url: str,
        base_dn: str,
        bind_dn: str,
        bind_password: str,
        user_filter: str,
        username_attr: str,
        email_attr: str,
        fullname_attr: str,
        db
    ) -> Dict[str, Any]:
        """Sync users from LDAP to local database."""
        if not HAS_LDAP3:
            return {"success": False, "error": "ldap3 not installed", "created": 0, "updated": 0}
        
        server = self._get_server(server_url)
        if not server:
            return {"success": False, "error": "Invalid server URL"}
        
        conn = self._get_connection(server, bind_dn, bind_password)
        if not conn:
            return {"success": False, "error": "Authentication failed"}
        
        try:
            # Search for users
            conn.search(
                search_base=base_dn,
                search_filter=user_filter,
                search_scope=SUBTREE,
                attributes=[username_attr, email_attr, fullname_attr, 'memberOf']
            )
            
            created = 0
            updated = 0
            errors = []
            
            for entry in conn.entries:
                try:
                    username = entry.username_attr.value if hasattr(entry, username_attr) else None
                    email = entry.email_attr.value if hasattr(entry, email_attr) else ""
                    fullname = entry.fullname_attr.value if hasattr(entry, fullname_attr) else ""
                    
                    if not username:
                        continue
                    
                    # Check if user exists locally
                    from app.models.auth import User
                    from sqlalchemy import select
                    
                    stmt = select(User).where(User.username == username)
                    result = await db.execute(stmt)
                    local_user = result.scalar_one_or_none()
                    
                    if local_user:
                        # Update existing user
                        local_user.email = email or local_user.email
                        local_user.full_name = fullname or local_user.full_name
                        updated += 1
                    else:
                        # Create new user
                        from app.services.auth_service import auth_service
                        # Generate a random password for LDAP users (they auth via LDAP)
                        import secrets
                        temp_password = secrets.token_urlsafe(16)
                        
                        new_user = await auth_service.create_user(
                            db,
                            username=username,
                            email=email,
                            full_name=fullname,
                            password=temp_password,
                            role="user"
                        )
                        created += 1
                    
                except Exception as e:
                    errors.append(f"Error processing entry: {str(e)}")
                    logger.error(f"LDAP sync error: {e}")
            
            conn.unbind()
            
            return {
                "success": True,
                "created": created,
                "updated": updated,
                "errors": errors
            }
            
        except Exception as e:
            return {"success": False, "error": str(e), "created": 0, "updated": 0}
    
    async def authenticate(
        self,
        server_url: str,
        base_dn: str,
        bind_dn: str,
        bind_password: str,
        username: str,
        password: str,
        username_attr: str
    ) -> Optional[Dict[str, Any]]:
        """Authenticate user against LDAP. Returns user data if successful."""
        if not HAS_LDAP3:
            return None
        
        server = self._get_server(server_url)
        if not server:
            return None
        
        # Try to bind with user credentials
        user_dn = f"{username_attr}={username},{base_dn}"
        
        try:
            conn = Connection(
                server,
                user=user_dn,
                password=password,
                authentication=SIMPLE,
                auto_bind=True
            )
            
            # Search for user details
            conn.search(
                search_base=base_dn,
                search_filter=f"({username_attr}={username})",
                search_scope=SUBTREE,
                attributes=['mail', 'cn', 'memberOf']
            )
            
            if conn.entries:
                entry = conn.entries[0]
                user_data = {
                    "username": username,
                    "email": str(entry.mail) if hasattr(entry, 'mail') and entry.mail else "",
                    "full_name": str(entry.cn) if hasattr(entry, 'cn') and entry.cn else username,
                    "groups": [str(g) for g in entry.memberOf] if hasattr(entry, 'memberOf') and entry.memberOf else []
                }
                conn.unbind()
                return user_data
            
            conn.unbind()
            return None
            
        except LDAPBindError:
            return None
        except Exception as e:
            logger.error(f"LDAP auth error: {e}")
            return None


# Singleton instance
ldap_service = LDAPService()
