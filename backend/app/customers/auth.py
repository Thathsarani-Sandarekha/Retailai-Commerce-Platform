from dataclasses import dataclass
from fastapi import Depends, Header, HTTPException, status

# Deliberate local-fixture auth. Replace with verified OIDC/JWT identities before deployment.
# Tenant identity comes from the credential mapping, NOT user-supplied tenant headers.
_DEMO_TOKENS = {
    "demo-northstar-agent": ("northstar", "agent", "northstar-agent-1"),
    "demo-northstar-manager": ("northstar", "manager", "northstar-manager-1"),
    "demo-river-agent": ("river", "agent", "river-agent-1"),
    "demo-river-manager": ("river", "manager", "river-manager-1"),
    # Synthetic customer identities only. No real customer authentication here.
    "demo-northstar-customer-c3": ("northstar", "customer", "northstar-customer-c3", "N-C3"),
    "demo-northstar-customer-c4": ("northstar", "customer", "northstar-customer-c4", "N-C4"),
    "demo-river-customer-c1": ("river", "customer", "river-customer-c1", "R-C1"),
}


@dataclass(frozen=True)
class Actor:
    tenant_id: str
    role: str
    id: str
    customer_id: str | None = None


def authenticate(x_demo_token: str | None = Header(default=None)) -> Actor:
    info = _DEMO_TOKENS.get(x_demo_token or "")
    if not info:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid demo token")
    return Actor(tenant_id=info[0], role=info[1], id=info[2],
                 customer_id=info[3] if len(info) > 3 else None)


def authenticate_staff(actor: Actor = Depends(authenticate)) -> Actor:
    if actor.role not in ("agent", "manager"):
        raise HTTPException(status_code=403, detail="Staff access required")
    return actor


def require_role(actor: Actor, role: str):
    if actor.role != role:
        raise HTTPException(status_code=403, detail=f"Requires {role} role")
